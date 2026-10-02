# pepa-console

One local web page for all the pepa workers. Pick a worker, fill in a form, and watch it run;
keys and folders are set once and handed to every worker. It runs each worker through its own
`manage.py` and answers only on this machine.

## How it works

```mermaid
flowchart TD
    USER["Web console"] -->|"run a command"| JOB["Job"]
    KEYS[("Keys and folders<br/>in the user profile")] -->|"environment variables"| JOB
    JOB --> CHILD[("Worker's manage.py<br/>in its own folder")]
    CHILD -->|"live output"| USER
```

| Page | What it does |
|---|---|
| Library | Counts PDFs, prepared texts and summaries, and runs the ticked workers in order |
| Apps | One page per worker, each command as a form with its live log, its run settings, and every file it reads or writes |
| Search | The pepa-read search page |
| Jobs | Every run since the console started |
| Folders | The project folder, and where each worker reads and writes |
| Models | Which model and server each worker writes and embeds with |
| Keys | Store a key once and choose which workers get it |
| Guide | How to start, and what each worker does |

## Setup

```powershell
pip install -r requirements.txt
python manage.py install
```

## Commands

| Action | Command |
|---|---|
| Open the web console | `python manage.py` |
| List every worker and its commands | `python manage.py status` |
| Run one worker command | `python manage.py run <app> <command>` |
| Check dependencies | `python manage.py install` |
