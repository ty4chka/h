# Upstream Heroku fixtures

`translations.py` is a compatibility fixture copied verbatim in content (with
line endings normalized) from
[`coddrago/Heroku`](https://github.com/coddrago/Heroku),
`heroku/modules/translations.py` (retrieved 2026-09-19).

It retains the upstream AGPLv3 notice at the top of the source file. The build
uses this checked-in fixture when a developer does not have a sibling
`../refs/heroku` checkout, so the offline acceptance run remains reproducible.
