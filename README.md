# Risk Tracker

Reads a weekly Notion positions page and prints a portfolio risk table. See
`PRD - Notion Position Risk Table.md` for the full spec.

## Setup

1. `pip install -r requirements.txt`
2. Create a Notion internal integration at https://www.notion.so/my-integrations
   and copy its token (`ntn_...`).
3. Open the week's Notion page, click **Share**, and invite the integration
   (or share it on the page's parent) so it can read the page. This is a
   one-time manual step per page/workspace.
4. Copy `.env.example` to `.env` and fill in `NOTION_URL`, `NOTION_TOKEN`,
   and `ACCOUNT_SIZE`. `.env` is gitignored — never commit it.

## Run

```
python main.py
```

Optional flags:

- `--csv PATH` — write unrounded rows to a CSV file
- `--json PATH` — write structured output to a JSON file
- `--sort {page,risk,size}` — row order (default `page`)
- `--verbose` — echo each line's parser classification, useful when a page
  parses oddly
- `--env-file PATH` — use a `.env` file other than the default

## Dashboard

A Streamlit dashboard is also available, showing the same data with a
color-coded risk column (green = no risk, red = still at risk, uncolored =
unresolved / no stop-loss). It reads the same `.env`.

```
streamlit run streamlit_app.py
```

Opens at http://localhost:8501. Use the **Refresh from Notion** button to
re-fetch after editing the page.

## Tests

```
python -m pytest
```
