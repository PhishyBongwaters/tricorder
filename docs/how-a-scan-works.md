# How a Scan Works

A plain-language walkthrough of what happens when you run
`tricorder /path/to/repo`. No code knowledge required.

## The short version

Tricorder reads your code, writes down every definition it finds
(functions, classes, methods) along with where each one lives, figures
out which ones matter most, trims the list to fit your token budget,
and prints the result. That printed list is the "map."

## Step by step

**1. Find the files.** Tricorder walks your repo and collects the source
files — it knows about 34 programming languages and ignores everything
else. If you passed `--exclude-globs` (say, `vendor/**`), those files
are skipped before anything else happens.

**2. Read each file and pull out the definitions.** Every file is parsed
and every definition is recorded: its name, what kind of thing it is
(function, class, method...), and the exact file and line number. Big
repos are read in parallel. Files it has already seen and that haven't
changed are skipped — only new or edited files get re-read.

**3. Sort out which class each method belongs to.** A method called
`run` inside `class Server` is recorded as `Server::run`, so it can't
be confused with some other `run` elsewhere.

**4. Stash it all in a small database.** Everything goes into a SQLite
database that lives in memory by default and disappears when the command
finishes. (Pass `--init` and it becomes a permanent database on disk
instead.)

**5. Decide what matters most.** Not all definitions are equal. Tricorder
ranks them with an algorithm similar to how search engines rank pages:
a function that gets called from fifty places outranks one nobody calls.
Files you're actively working on get an extra boost.

**6. Fit it into your token budget.** The ranked list is trimmed until it
fits `--map-tokens` (default 8192 tokens) — the highest-ranked
definitions survive. This is the step that keeps a 16GB local model from
drowning: it sees the important parts first, and only the important
parts.

**7. Print the map.** The final ranked list goes to stdout — that's what
you (or your agent) read.

## What changes on the second run

Almost nothing is re-read. Each file's fingerprint (path, size,
modification time) is checked, and only changed files go through step 2
again. A second scan of an untouched repo is fast.

## The first "tell me more" question

Commands like `detail` and `graph_query` ("who calls this function?")
need one extra index: which files import which, and every place each
name is mentioned. Building it means reading every file twice more —
once for imports, once for mentions. This costs **time, not tokens**:
parsing happens on your machine and nothing is sent to the model. The
index is saved to disk afterwards, so you pay this once per repo. On a
very large repo (10k+ files) expect the first such query to take
minutes — that's the index building, not a hang.

## Why it's built this way

Each step exists to serve the same goal: **give an AI the useful parts
of a repo without blowing its context window.** Finding files narrows
the universe. Parsing extracts structure instead of raw text. Ranking
puts the important things first. The token budget guarantees the output
fits. The caches make repeat visits cheap. The whole pipeline is a
funnel: repo in, focused map out.
