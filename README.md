# sonolus-level-converters
Convert between Sonolus LevelData (as well as MMW4CC's USC and Sekai's SUS). Can also be used to easily read chart data.

Requires `Python >= 3.10`

# Fully Supported
Any file type listed here supports conversions between and from.
- `.usc`
- `.sus`
- `.mmws`
- `.ccmmws`
- `.unchmmws`

- `chart_cyanvas LevelData` - (returns a identical copy of the original usc, except without time signatures) **hold mids are broken**

# Partial Support
Any file type listed here will have some support.
- `pjsekai LevelData` - Exporting only
- `next_sekai LevelData` - Exporting only
- `untitled_sekai LevelData` - Exporting only

# Utils/Helpers
- Strip ChCy Extended Features
- Skills/Fever conversions

# Known Issues
- Chart Cyanvas LevelData loading is broken with holds. Converting a Score made from this to sus makes a invalid hold. Converting a Score made from this to usc has extra hold mids.
- PJSK LevelData is not tested and likely wrong.

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

@hyeon2006 for the help

@YarNix for the help and MMWS loaders/exporters

@qwewqa for the Next Sekai exporter