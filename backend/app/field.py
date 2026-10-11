"""The Worlds 2026 field: teams, regions, pools and name aliases.

Kept as YAML text inside a Python module because Vercel's Python bundler ships .py files
but not data files: a separate worlds2026.yaml was missing at runtime there. Edit the
YAML below. Set WBS_WORLDS_CONFIG to a file path to override it.
"""

WORLDS_2026_YAML = """\
# Worlds 2026 field, per Riot's Worlds 2026 primer as reported by RFT.GG.
# Verify against https://lolesports.com/news/worlds-2026-primer before relying on it.
# `aliases` are used to match team names coming from gol.gg, Oracle's Elixir and Polymarket.
# CBLOL: LØS won the Oct 10 final (Swiss pool 2); FURIA, the runner-up, plays the Play-In.

tournament: Worlds 2026
western_regions: [LEC, LCS, CBLOL]

play_in:
  advance: 1          # winner goes to Swiss pool 4
  best_of: 5
  teams: [KC, C9, MVK, FURIA]

swiss:
  pools:
    1: [GEN, AL, TL, G2]
    2: [LOS, TSW, HLE, BLG]
    3: [LYON, MKOI, T1, TES]
    4: [CFO, IG, DK, PLAYIN_WINNER]
  wins_to_advance: 3
  losses_to_eliminate: 3
  # round 1: pool 1 vs pool 4, pool 2 vs pool 3, no same-region matchups
  # later rounds: same record, no rematches, same region allowed
  # Bo3 when the match decides advancement or elimination, else Bo1

knockout:
  best_of: 5
  # 3-0 teams are each drawn against a 3-2 team; the rest pair 3-1 vs 3-1 / 3-2

teams:
  GEN:    {name: Gen.G,                region: LCK,   aliases: [Gen.G, GenG, Gen.G Esports, GEN]}
  HLE:    {name: Hanwha Life Esports,  region: LCK,   aliases: [Hanwha Life Esports, Hanwha Life, HLE]}
  T1:     {name: T1,                   region: LCK,   aliases: [T1, SK Telecom T1]}
  DK:     {name: Dplus KIA,            region: LCK,   aliases: [Dplus KIA, Dplus Kia, DK, Dplus]}
  AL:     {name: Anyone's Legend,      region: LPL,   aliases: ["Anyone's Legend", Anyones Legend, AL]}
  BLG:    {name: Bilibili Gaming,      region: LPL,   aliases: [Bilibili Gaming, BLG]}
  TES:    {name: Top Esports,          region: LPL,   aliases: [Top Esports, TOP Esports, TES]}
  IG:     {name: Invictus Gaming,      region: LPL,   aliases: [Invictus Gaming, IG]}
  G2:     {name: G2 Esports,           region: LEC,   aliases: [G2 Esports, G2]}
  MKOI:   {name: Movistar KOI,         region: LEC,   aliases: [Movistar KOI, KOI, MKOI, Mad Lions KOI]}
  KC:     {name: Karmine Corp,         region: LEC,   aliases: [Karmine Corp, KC, Karmine]}
  TL:     {name: Team Liquid,          region: LCS,   aliases: [Team Liquid Alienware, Team Liquid, TL, Liquid]}
  LYON:   {name: LYON,                 region: LCS,   aliases: [LYON, Lyon Gaming, LYON Gaming]}
  C9:     {name: Cloud9,               region: LCS,   aliases: [Cloud9, C9, Cloud9 Kia]}
  TSW:    {name: Team Secret Whales,   region: LCP,   aliases: [Team Secret Whales, TSW, Team Whales]}
  CFO:    {name: CTBC Flying Oyster,   region: LCP,   aliases: [CTBC Flying Oyster, CFO, Flying Oyster]}
  MVK:    {name: MVK Esports,          region: LCP,   aliases: [MVK Esports, MVK]}
  LOS:    {name: LØS,                  region: CBLOL, aliases: [LØS, LOS, LØS Esports]}
  FURIA:  {name: FURIA,                region: CBLOL, aliases: [FURIA, FURIA Esports]}
"""
