# UI texts (monitoring pages)

All user-visible texts of the monitoring pages (`WS/uha*.html`) come from `texts.json`, built from Martin's
dictionary `uha_ui_dict.xlsx`. The pages contain no text of their own, only keys.

## Updating after a change of the dictionary

1. Save the spreadsheet as `WS/i18n/uha_ui_dict.xlsx` (same sheets and column headers; columns may move).
2. Run (PC, Python 3, no extra package needed for the xlsx; PyYAML for the enum map):

   ```bash
   python UHA/tools/dict_to_texts.py
   ```

3. Commit `uha_ui_dict.xlsx` + `texts.json` and copy `texts.json` to the Pi (`/home/pi/Web/i18n/`).

That is the whole procedure. The script prints the counts and, if any, the keys still waiting in
`texts_pending.json` (see below).

## Files

| File | Content |
|---|---|
| `uha_ui_dict.xlsx` | the source (Martin edits it): sheets `UI texty`, `Proměnné YAML`, `Příkazy YAML`, `Enumy YAML` |
| `texts.json` | generated, read by `js/uha-common.js`: `ui`, `vars`, `cmds`, `enums`, `var_enums` |
| `texts_pending.json` | texts the pages need that the dictionary does not have yet (added by the agent). Merged into `texts.json`, the dictionary wins. When a key is added to the sheet `UI texty`, the script says so - then delete it here. |

`var_enums` (which enum a variable uses) is read from `uha_vars.yaml` in the UHA_FW repo
(`../UHA_FW/UHA_COMMON/VarDefs/`, or set `UHA_VARS_YAML`); without it the previous map is kept.

## In the pages (`js/uha-common.js`)

- `U.t('mon.home.today')` - UI text; `{x}` placeholders: `U.t('mon.home.charging', {x: '650 W'})`
- `U.vname('BAT_VOLTAGE_V')` - full name ("Baterie – napětí"), where the context is missing (All data, tooltips)
- `U.vshort('POW_KITCHEN_W')` - short name ("Kuchyň"), in a card that already names the measure
- `U.vmeasure('STRG1_VOLTAGE_V')` - the part after " – " of the full name ("Napětí"), in a card that names the area
- `U.enumText('ST_BOILER_STATE')` - enum item in the current language
- Variables of an array use `{n}` in the dictionary: `BMS1_CELL_V_{n}` covers `BMS1_CELL_V_1` … `_16`.
- A missing key is shown as the key itself and listed once in the browser console
  (`UHA: n text(s) missing in i18n/texts.json: …`).

Language: CZ default, EN in the menu (☰), remembered in the browser (`localStorage` `uha.lang`). Numbers follow
the language (cs: decimal comma, space as thousands separator).
