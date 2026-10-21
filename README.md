# Mealime export

Mealime is shutting down. This saves your recipes as markdown (ingredients, steps, cookware, nutrition) plus the raw JSON and the main photo.

1. Save recipe share URLs to `iCloud Drive/mealime/urls.txt`, one per line, using a share-sheet shortcut ([build it yourself](SHORTCUT.md), two actions).
2. Run `mealime_export.py` on that file.

```bash
python3 mealime_export.py "$HOME/Library/Mobile Documents/com~apple~CloudDocs/mealime/urls.txt" [out_dir]
```

Python 3, stdlib only. The script makes plain HTTPS GETs to the URLs you list and writes files under `out_dir` (default `./mealime-export`). Failed URLs go to `failed.txt` in `out_dir`, which you can feed back in.

## Limits

- Run it before Mealime shuts down. If `r.mealime.com` goes offline, nothing can be fetched.
- It reads public share URLs only. Private meal plans, grocery lists and anything behind a login are not covered.
- It depends on the recipe JSON embedded in the page (`__NEXT_DATA__`). If Mealime changes that shape, `extract()` breaks.
- Exported recipes are Mealime's and their authors' content. This is for personal archiving; don't republish them.

## The shortcut

No prebuilt `.shortcut` file is shipped, because signed shortcut binaries can't be reviewed. [SHORTCUT.md](SHORTCUT.md) lists the two actions to build by hand. `shortcut/decoded.plist` is the XML dump of the original shortcut the guide was written from (two iCloud account IDs redacted); grep it for the action identifiers named in the guide.

## License

MIT. Not affiliated with or endorsed by Mealime.
