# Source lineages

| Lineage | Full source identity | Relationship / artifact evidence |
|---|---|---|
| A9 common base | 2e6520d5b6a7874881e5de85dbb6ececaef11d8f | Published genesis-a9-20261101; preserved |
| Original continuity | a63068de10a111a7784bcf677101a66b693d0908 |15 commits after A9; original System Control Center branch; preserved |
| CORE NEXT published |953b67fa50dfa9d705f060f97b8a1af5d317c001 | Published v0.5.0-dev.1-core-next;15 assets |
| CORE NEXT F |ede5bf788097abc136eee2ae726248893fb4ae7b |10 commits after A9, six after published953; frozen dev.4 r2 packages; not published |
| Nested foundation |1d044992d36962359dfe46b4caedef750a3c0043 | Independent dragon-football0.1.0 history;70 tracked files; no shared ancestor |
| Installed backend/native/profile |3af173d0248e95f7d76aeabed1095aa4f3e97af3 |dev.3, build upgrade-3af173d0248e; not the F backend |
| Installed Joomla component/template/package |ede5bf788097abc136eee2ae726248893fb4ae7b |dev.4, supported scoped CLI update/repeat; protected cached application ZIP still dev.3 |

A9 is the exact common ancestor of original and F. Neither tip contains the
other. A newer commit, recent push or shared version label is not proof of installed
binary identity. The integration branch starts at F and selectively recovers
compatible behavior rather than merging all original files or flattening source/.
Private bundles preserve every captured reachable ref; reflog-only/unreachable
objects and external LFS content are outside the verified bundle scope.
