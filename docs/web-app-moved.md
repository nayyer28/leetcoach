# Web app planning moved

The web app is its own product, in its own repo:

`~/repos/non-work/leetcoach-web/`

The design spec, STATUS, CLAUDE.md, and all future implementation work
live there. This bot repo (`leetcoach`) keeps running as-is; nothing
shared at runtime.

Application + infrastructure layers (`leetcoach/services/`,
`leetcoach/storage/`) will be *lifted* (copied) into the web repo's
`core/` during implementation. No shared package, no submodule.
