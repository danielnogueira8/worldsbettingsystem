# Match data

`2026_team_rows_tier1.csv.gz` is an extract of Oracle's Elixir's 2026 League of Legends
esports match data (https://oracleselixir.com/tools/downloads): only the two team rows
per game, only tier-1 leagues and international events, only the columns the loader
reads. Data by Oracle's Elixir.

To refresh it, download the latest 2026 file and rebuild the extract, or point
`wbs load-oracles` at the full file directly.
