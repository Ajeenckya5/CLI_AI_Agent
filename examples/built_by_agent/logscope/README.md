# LogScope

LogScope is a small command-line log analysis tool. It reads JSONL logs or common
plain-text application logs, then produces level counts, service counts, status
code counts, timelines, and burst detection.

This example is intentionally dependency-free so it can run anywhere Python runs.

## Usage

```bash
python3 logscope.py sample.log
python3 logscope.py sample.log --level ERROR --top 3
python3 logscope.py sample.log --service api --bucket minute
python3 logscope.py sample.log --json
```

## Tests

```bash
python3 -m unittest discover -s .
```

