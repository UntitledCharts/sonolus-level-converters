# sonolus-level-converters
Convert between Sonolus LevelData

Currently supported:
- MikuMikuWorld4CC .usc files
- PJSK Implementations of .sus files

TODO:
- SekaiRush/PJSEKAI LevelData (to and from)
- Chart Cyanvas LevelData (to and from)
- PySekai LevelData (to)
- PySekai LevelData (from) (is this possible??)
- Strip extended features:
    - Strip pysekai extended (to convert to chcy)
    - Strip chcy extended (to convert to base game)
- Fix typing for color, and convert to base game correctly (USCs support more than YELLOW/GREEN color, while base game supports more)
- Sonolus USC file (I don't actually believe this is needed, low priority)


# Credit
[susc-converter](https://github.com/Kyonkrnk/susc-converter/) for the base

[sonolus-pjsekai-js](https://github.com/hyeon2006/sonolus-pjsekai-js/blob/main/lib/src/usc/revert.ts) for the uscToUsc converter

@YarNix and @hyeon2006 for the help