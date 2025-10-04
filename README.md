# sonolus-level-converters
Convert between Sonolus LevelData (as well as MMW4CC's USC and Sekai's SUS)

Requires `Python >= 3.10`

# Fully Supported
Any file type listed here supports conversions between and from.
- `.usc`
- `.sus`
- `chart_cyanvas LevelData` - (returns a identical copy of the original usc, except without time signatures)

# Partial Support
Any file type listed here will have some support.
- `pjsekai LevelData` - Exporting only
- `next_sekai LevelData` - Exporting only
- `untitled_sekai LevelData` - Exporting only

# Utils/Helpers
- Strip ChCy Extended Features

# ToDo
- pjsekai LevelData (from)
- PySekai LevelData (from) (is this possible??)
- Strip extended features:
    - Strip pysekai extended (to convert to chcy)
- Sonolus USC file (I don't actually believe this is needed, low priority)

# All Sekai LevelDatas, and their servers (including level packers)
- pjsekai LevelData
    - PJSekai (sonolus.sekai.best)
    - Potato Leaves Archive (ptlv.sevenc7c.com)
    - Sekai Rush (shut down)
- Chart Cyanvas LevelData
    - Chart Cyanvas Archive (cc.sevenc7c.com)
- Next Sekai LevelData
    - UntitledCharts (untitledcharts.com)
    - Next Sekai (coconut.sonolus.com/next-sekai)
- UntitledSekai LevelData
    - UntitledSekai (us.pim4n-net.com)

# Credit
[susc-converter](https://github.com/Kyonkrnk/susc-converter/) for the base

[sonolus-pjsekai-js](https://github.com/hyeon2006/sonolus-pjsekai-js/blob/main/lib/src/usc/revert.ts) for the uscToUsc converter

@YarNix and @hyeon2006 for the help