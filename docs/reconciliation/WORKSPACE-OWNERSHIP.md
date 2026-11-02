# Source and runtime ownership

| Boundary | Current owner / identity | Integration rule |
|---|---|---|
| C:/xampp/DRAGONHYDRA | Independent .git, continuity/genesis-20261031-a6 at a63068de; one modified tracked document, nine regular untracked files plus nested source boundary | Read-only preservation/reference; no cleanup, reset or installation writes |
| C:/xampp/DRAGONHYDRA-CORE-NEXT | Independent .git; reconcile/genesis-20261102 from F ede5bf | Single integration checkout; task-owned source only |
| C:/xampp/DRAGONHYDRA/source | Independent .git, main at1d044992, no common ancestor, clean | Preserve separately; abstract analytical foundation is research, not a replacement application |
| CORE NEXT LAB | Private profiles, evidence, snapshots, isolated test/build outputs | Never release runtime credentials/databases/backups |
| Primary CORE NEXT | profile core-next-7ac520727b85456cac4a3a92a8dd62da; LocalService DragonhydraCoreNextcandidate3a92a8dd62da; API18821/Joomla18822/MariaDB18823 | Only authorized deployment target after isolated acceptance |
| Original profiles | Joomla18740/API18744 plus independent18743,18747,18750 installations | Preserve service PIDs/configuration/state; never repoint to the first responsive API |

The three source roots are ordinary physical directories, not root junctions.
All six historical detached worktrees recorded by the original repository were
queried with optional Git locks disabled and are clean: release-source2e6520d,
source4a08f87, source-s246ba85c, Android5ba45bb/d10c10f/a138054.
Their full paths and identities are in LAB original-worktree-state-r1.json.

Task ownership is explicit and narrow: frontend model/template/filter seams;
Python typed observation plus existing supervisor heartbeat; packaging input
validation; coordinator documentation/integration. Separate Git metadata does not
imply separate services or databases. No generic session coordinator is introduced.
