# Introduction
If you want to iterate through a bunch of GraphQL mutations, you can use graphql.py. It can either:
1. Run one query or mutation against a list of IDs
1. Run a list of queries or mutations

It requires three environment variables to be set or defined in a `.env` file:
- `URI` is the URI of the GraphQL endpoint.
  - Example: `URI=https://example.sonar.software/api/graphql`
- `BEARER_TOKEN` is the BEARER_TOKEN Personal Access Token.
  - Example: `BEARER_TOKEN="...."`
- `CONCURRENT_REQUESTS` is the number of concurrent requests to throw at Sonar. 
  - Example: `CONCURRENT_REQUESTS=40`

See `example.env` for an example.

## Usage
It has two different ways of running it:
1. [List of IDs](#list-of-ids)
2. [List of mutations](#list-of-mutations)

### List of IDs
The first way of using it is to specify a list of IDs to process the same mutation on.

Let's say you have 100 IDs that all need the same mutation run against them, for example, you want to change all the account status IDs to 1 (Active):

```graphql
mutation {
  updateAccount (id:X, input:{
    account_status_id:1
  }) {
    id
  }
}
```

You would change the `X` above to `%i` and run it against the specified IDs.

#### Example
A common way to run this is to put a list of IDs in a text file, and run it with that. Let's say we have the following two files:

`updateAccountStatuses.graphql` which might consist of:

```graphql
mutation {
  updateAccount (id:%i, input:{
    account_status_id:1
  }) {
    id
  }
}
```

`ids_to_update.txt` which might consist of:
```
1-5
10
23
76
```

You could run all those IDs above against the mutation above, by running:

```sh
./graphql.py -i updateAccountStatuses.graphql $(cat ids_to_update.txt)
```

### List of mutations

Let's say you have a bunch of mutations to run, perhaps created by an Excel CONCATENATE function. The lines might look like this:

```graphql
mutation { updateContact (id:16, input: { username: "joe", password: "b4f0a6ea3" }) {created_at contactable_id username email_address } }
mutation { updateContact (id:256, input: { username: "ralph", password: "feb3a43b2ea" }) {contactable_id username email_address } }
mutation { updateContact (id:1024, input: { username: "hank", password: "3ee024c9c9e6" }) {contactable_id username email_address } }
```

Save the list of mutations, one per line. Let's call the file `updateContacts.graphql`. Run it like:

```sh
./graphql.py updateContacts.graphql
```

## Options

Like any decent UNIX-like utility, it has some options. You can get these by running `graphql.py --help` but I will give more detail here...

- `-l FILENAME` logs to a particular filename. If you don't specify the logfile, it will still log, but to a default file in the directory you ran it from, called `graphql-YYYYMMDDhhmmss.log` where the `YYYMMDDhhmmss` is the timestamp of when you ran it
- `-i FILENAME` is really only in case you're running a single mutation against a list of IDs, rather than if you're running a file that has one mutation per line. It specifies the input mutation (or query) rather than prompting you for it or reading it from stdin.
- `-c #` overrides the concurrency you have set in your .env file. The # is a number (for example, 1)
- `-r #` sets the number of retries if it doesn't get a response from the server. Default is 3.
- `-s` forces it to stop when it hits an error of any kind. Note that it will still wait for a response from the server for already-queued items
- `-d` disables logging. Not sure why you'd want to do that, to be honest.

## Tips and Tricks
- Run this from a `screen` session to protect yourself from connectivity issues with your ssh session.
- What's logged to the screen and the output file is the same thing.
- Name your output file (using the `-l LOGFILE` switch described above) to log it to the same base filename as your list of mutations. For example:
```sh
graphql.py -l updateContacts.log updateContacts.graphql
```
- Indicate a timestamp in your log so you can go back into the logs and see exactly when you did something (note the datetime stamp will be in UTC regardless of what timezone is set on the instance).
  - If you're running an `update` mutation, make one of the outputs `updated_at`.
  - If you're running a `create` mutation, make one of the outputs `created_at`.
  - Examples:
```graphql
mutation { updateContact(id: 16, input: {username: "joe", password: "b4f0286ea3"}) { id contactable_id updated_at } }
mutation { createContact (input:{ contactable_type:Account contactable_id:1 name:"Din Djarin" }) { id contactable_id created_at } }
```

While you can do queries using this tool, it's really made for doing mutations. The output is not pretty-printed.