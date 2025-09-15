# sonolus-level-converters
Convert between Sonolus LevelData (as well as MMW4CC's USC and Sekai's SUS)

# Fully Supported
Any file type listed here supports conversions between and from.
- `.usc`
- `.sus`

# Partial Support
Any file type listed here will have some support.
- `pjsekai LevelData` - Exporting: everything except guides
- `chart_cyanvas LevelData` - Exporting: everything except slides

# ToDo
- pjsekai LevelData (from, fix guides)
- Chart Cyanvas LevelData (to and from)
- PySekai LevelData (to)
- PySekai LevelData (from) (is this possible??)
- Strip extended features:
    - Strip pysekai extended (to convert to chcy)
    - Strip chcy extended (to convert to base game)
        - colors
- Fix typing for color, and convert to base game correctly (USCs support more than YELLOW/GREEN color, while base game supports more)
- Sonolus USC file (I don't actually believe this is needed, low priority)

# All Sekai LevelDatas, and their servers (including level packers)
- pjsekai LevelData
    - PJSekai (sonolus.sekai.best)
    - Potato Leaves (ptlv.sevenc7c.com)
    - Sekai Rush (shut down)
- Chart Cyanvas LevelData
    - Chart Cyanvas (shut down)
- Next Sekai / PySekai LevelData
    - UPCOMING
- UntitledSekai LevelData
    - UntitledSekai (us.pim4n-net.com)

# Credit
[susc-converter](https://github.com/Kyonkrnk/susc-converter/) for the base

[sonolus-pjsekai-js](https://github.com/hyeon2006/sonolus-pjsekai-js/blob/main/lib/src/usc/revert.ts) for the uscToUsc converter

@YarNix and @hyeon2006 for the help