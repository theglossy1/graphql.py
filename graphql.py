#!/usr/bin/env python3.8

####
#
#  Written by:
#    - Josiah Glosson (josiahmglosson@gmail.com)
#    - Matt Glosson (matt.glosson@gmail.com)
#
####

import argparse
import datetime
import itertools
import os
import sys
import time
import warnings

try:
    import crashreport
    import dotenv
    from aiohttp.client_exceptions import ContentTypeError
except ModuleNotFoundError:
    print("Please install all the required dependencies by running:")
    print(f'{sys.executable} -m pip install -Ur requirements.txt')
    sys.exit(1)


class MultiIterContext:
    contexts: list

    def __init__(self, *contexts) -> None:
        self.contexts = list(contexts)

    def __enter__(self):
        for (i, context) in enumerate(self.contexts):
            self.contexts[i] = context.__enter__()
        return self

    def __exit__(self, *args):
        for context in self.contexts:
            context.__exit__(*args)

    def __iter__(self):
        return itertools.chain.from_iterable(self.contexts)

    def __len__(self):
        return sum(1 for _ in self)


def graphql_help(quitter=True):
    helpText =  f"{os.path.basename(sys.argv[0])} : Run a bunch of GraphQL commands on certain numbers.\n  reads from environment\n\n"
    helpText += f"\tSyntax:  {sys.argv[0]} [options] IDs\n"
    helpText += f"\tExample: {sys.argv[0]} 1 5 10 100-200\n"
    helpText += f"\tAction:  Will run a query/mutation against %i varible, substituting 1,5,10,100,101,102...200\n\n"
    helpText += f"\tSyntax:  {sys.argv[0]} [options] <filename-to-read-GraphQL-lines-from>\n"
    helpText += f"\tExample: {sys.argv[0]} myMutation.graphql\n"
    helpText += f"\tAction:  Will run queries/mutations line-by-line in the specified filename\n\n"
    helpText += f"Run {os.path.basename(sys.argv[0])} --help for more help.\n"
    helpText += "Also see https://github.com/theglossy1/graphql.py"
    if quitter:
        print(helpText)
        quit()
    else:
        return helpText


def id_type(val):
    if os.path.exists(val):
        if os.path.isdir(val):
            raise argparse.ArgumentTypeError('File path is a directory')
        return val
    if '-' in val:
        vals = val.split('-')
        lower, upper = int(vals[0]), int(vals[1])
        return range(lower, upper + 1)
    else:
        val = int(val)
        return range(val, val + 1)


def make_wide(formatter, w=120, h=36):
    """Return a wider HelpFormatter, if possible."""
    try:
        kwargs = {'width': w, 'max_help_position': h}
        formatter(None, **kwargs)
        return lambda prog: formatter(prog, **kwargs)
    except TypeError:
        warnings.warn("argparse help formatter failed, falling back.")
        return formatter


default_logfile = os.path.splitext(os.path.basename(sys.argv[0]))[0]

parser = argparse.ArgumentParser(
    description=__doc__,

    formatter_class=make_wide(argparse.HelpFormatter, w=100)
)
parser.add_argument("-u","--usage", action="store_true", dest="usage", help="Show usage and examples, then exit")

parser.add_argument("-l","--logfile", metavar="FILENAME", action="store", dest="logfile",
    help=f"Specify logfile; default is {default_logfile}-YYYYMMDDhhmmss.log",
    default=f"{default_logfile}-{time.strftime('%Y%m%d%H%M%S')}.log")
parser.add_argument("-i","--input", metavar="FILENAME", type=argparse.FileType('r', encoding='utf-8'),
    dest="file", help="Specify filename containing GraphQL query rather than reading from stdin")
parser.add_argument("-c","--concurrency", metavar="COUNT", action="store", dest="concurrency", help="Concurrent requests to run; overrides value from environment",
        default=None, type=int)
parser.add_argument("-r", "--retries", metavar="RETRIES", action="store", dest="retries", help="Number of retries if an item fails to get a response from the server. 0 means don't retry at all. Default is 3",
        default=3, type=int)
parser.add_argument("-s", "--stop", action="store_true", dest="stop", help="Stop processing after hitting a failure (note, the program will wait for a response from the server for already-queued items)")
parser.add_argument("-d", "--disable-logging", action="store_false", dest="do_logging", help="Disable log file and only output to stdout")
parser.add_argument('IDs', metavar="IDs|FILE", nargs="*", type=id_type, help="If using IDs, you can specify a range like 1-8, individual like 4 8 16 or a mix like 1-8 12 24. If using a file to read queries from, put the filename")
args = parser.parse_args()

def get_ids(ids):
    for item in ids:
        if isinstance(item, range):
            yield from item
        else:
            yield item

if args.usage:
    graphql_help()

if not args.IDs:
    graphql_help()

def ctrlc(etype, value, tb, dump_path):
    "Ctrl+C handler"
    if isinstance(value, KeyboardInterrupt):
        state.stop_immediately = True
    elif isinstance(value, Exception):
        name_to_show = ''
        for char in value.__class__.__name__:
            if char.isupper():
                name_to_show += ' '
            name_to_show += char.lower()
        name_to_show = name_to_show.strip().capitalize()
        message = f'A fatal error occured: {name_to_show}\n'
        message += f'Crash dump saved to: {dump_path}'
        print(message, file=sys.stderr)
        if log_handler is not None:
            print(message, file=log_handler)
        sys.exit(1)

def error():
    print(f"First parameter must be a number; for help run:\n\t{sys.argv[0]} -h")
    quit()

dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))
URI = os.environ.get('URI')
BEARER_TOKEN = os.environ.get('BEARER_TOKEN')
concurrent_requests = (
    int(os.environ.get('CONCURRENT_REQUESTS', 1))
    if args.concurrency is None
    else args.concurrency
)

for requiredVar in ('URI', 'BEARER_TOKEN'):
    if globals()[requiredVar] is None:
        print(requiredVar, "not defined in environment")
        quit()

# Ctrl+C handling
crashreport.inject_excepthook(ctrlc)

varList = list(get_ids(args.IDs))

if args.do_logging:
    try:
        log_handler = open(args.logfile, "w", buffering=1)
        print(f"Logging to", args.logfile)
    except:
        print(f"Couldn't open {args.logfile} for writing; aborting!")
        quit()
else:
    log_handler = None

uniform_type = type(varList[0])
for id in varList:
    if not isinstance(id, uniform_type):
        if uniform_type == int:
            type_name = 'IDs'
        elif uniform_type == str:
            type_name = 'files'
        else:
            type_name = uniform_type.__qualname__
        print('Arguments are not all', type_name)
        exit(1)

if uniform_type == int:
    totalIDs = len(varList)
    padding = len(str(max(varList)))

    if args.file is not None:
        query = args.file.read()
    else:
        print(f"""Paste your GraphQL query or mutation below, and put a . on a line by iteself to execute. For the iterator #, use %i
    If you want to know what this program is all about before proceeding, hit Ctrl+C and run {os.path.basename(sys.argv[0])} -h\n----""")
        query = ''
        for line in sys.stdin:
            if line.strip() == '.':
                break
            query += line

    if '%i' not in query:
        print("There was no %i in the query... perhaps you should run it via GraphiQL")
        quit()
elif uniform_type == str:
    totalIDs = 0
    line_count = 0
    with MultiIterContext(*(open(file, encoding='utf-8') for file in varList)) as fps:
        for line in fps:
            totalIDs += bool(line.strip())
            line_count += 1
    padding = len(str(line_count))


import asyncio
import types

import aiohttp
import colorama

max_requests = 1 if args.stop else args.retries + 1
responseList = []
lineList = []

async def doQuery(state, sess: aiohttp.ClientSession, queryText, id):
    global responseList
    while state.activeTasks >= concurrent_requests:
        await asyncio.sleep(0)

    async def internal():
        state.activeTasks += 1
        async with sess.post(URI, json={'query': queryText}) as resp:
            state.activeTasks -= 1
            if resp.status != 429:
                state.doneTasks += 1
            percentComplete = round(state.doneTasks/totalIDs*100, 1)
            message = f"Processed {id:<{padding}} ({percentComplete:5}% complete) - "
            responseList.append(id)
            error_code = resp.status
            try:
                json = await resp.json()
            except (ContentTypeError, UnicodeDecodeError):
                json = await resp.text(errors='replace')
                failed_json = True
            else:
                failed_json = False
            if resp.status != 200:
                color = ('\u001b[31;1m', '\u001b[0m')
                message += f"Error: response code on query '{queryText}' was {resp.status} "
            elif failed_json:
                color = ('\u001b[31;1m', '\u001b[0m')
                message += f"Error: unable to decode JSON on query '{queryText}' "
                error_code = -1
            elif 'errors' in json:
                color = ('\u001b[31;1m', '\u001b[0m')
                message += f"Got error response on query '{queryText}' : "
                error_code = -1
            else:
                color = ('', '')
            message += str(json)
            print(f'%s{message.replace("%", "%%")}%s' % color)
            if log_handler is not None:
                print(message, file=log_handler)
            return error_code
    backoff = 1
    for tries in range(max_requests):
        if state.stop_immediately:
            state.doneTasks += 1
            return -1
        resp_code = await internal()
        if state.stop_immediately:
            return resp_code
        if args.stop and resp_code != 200:
            state.stop_immediately = True
            return -1
        if resp_code == 429:
            if tries + 1 < max_requests:
                message = ' '*10 + f'{id:<{padding}} failed ({max_requests - tries} retry(s) remaining). Retrying in {backoff} seconds...'
                print('\u001b[33;1m' + message + '\u001b[0m')
                if log_handler is not None:
                    print(message, file=log_handler)
                await asyncio.sleep(backoff)
                backoff *= 2
        else:
            return resp_code
    state.doneTasks += 1
    message = ' '*10 + f'{id:<6} failed {max_requests} times. It will not be retried.'
    print('\u001b[31;1m' + message + '\u001b[0m')
    if log_handler is not None:
        print(message, file=log_handler)
    return -1


state = types.SimpleNamespace()
async def main():
    tasks = []
    state.doneTasks = 0
    state.activeTasks = 0
    state.stop_immediately = False

    global lineList

    startTime = datetime.datetime.now()
    message = f'Processing {totalIDs} lines/IDs with {concurrent_requests} concurrent {"request" if concurrent_requests == 1 else "requests"} on {URI} at {startTime}'
    print(message)
    if log_handler is not None:
        print(message, file=log_handler)
    async with aiohttp.ClientSession(headers={
        'Authorization': f'Bearer {BEARER_TOKEN}'
    }) as sess:
        if uniform_type == int:
            for varNumber in varList:
                queryText = query % ((varNumber,) * query.count('%i'))
                tasks.append(asyncio.create_task(doQuery(state, sess, queryText, varNumber)))
        else:
            with MultiIterContext(*(open(file, encoding='utf-8') for file in varList)) as fps:
                for (i, line) in enumerate(fps):
                    line = line.strip()
                    lineList.append(i+1)
                    # print(f"Line {i+1} - {line}")
                    if line:
                        tasks.append(asyncio.create_task(doQuery(state, sess, line, i + 1)))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = results.count(200)  # count the number of 200 OK http responses

    failures = set()
    if successes == totalIDs:
        color = '\u001b[32;1m'
    else:
        color = '\u001b[33;1m'
        if uniform_type == int:
            for var in varList:
                if var not in responseList:
                    failures.add(var)
            error_summary = "Never heard back from: " + ','.join([str(x) for x in sorted(list(failures))]).rstrip(",")
        else:
            for var in lineList:
                if var not in responseList:
                    failures.add(var)
            error_summary = "Never heard back from the following input lines: " + ','.join([str(x) for x in sorted(list(failures))]).rstrip(",")


    message = f"{successes}/{totalIDs} requests succeeded"
    if args.do_logging:
        message += f" and logged to '{args.logfile}'"
    message += f". Time taken: {datetime.datetime.now() - startTime}"
    if len(failures):
        message += f"\n{error_summary}"
    # message += f"\nLine count: {line_count}; totalIDs:{totalIDs} successes: {successes}"
    # message += "\nLine List: " + ','.join([str(x) for x in lineList])
    # message += "\nResponse List: " + ','.join([str(x) for x in responseList])

    print(color + message + '\u001b[0m')
    if log_handler is not None:
        print(message, file=log_handler)


if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
with colorama.colorama_text():
    asyncio.run(main())
