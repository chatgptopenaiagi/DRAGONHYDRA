# Context AI preservation checkpoint

2026-10-31. Engineering stopped on explicit user steering. No pending installed preflight, installer, service, HTTP, browser or model action is authorized by this note. No Git mutation was performed by the offline-AI reviewer.

The source package/3 core, exact immutable reader, API opt-in and UI are retained. The source suite previously passed 557 tests (including the nine probe tests); the new installed-helper guard suite separately passed eleven offline tests. The actual source Qwen/API probe accepted F1/E1 with all four input IDs. Three context citations were exercised using labelled synthetic completion fixtures; this does not establish Qwen selecting a C1 count fact.

A6 is built and extracted, with 28 frozen smoke groups, 68 source inputs and 710 kernel files reported verified by root/packaging. It has NOT been applied to the existing test workstation. The last accepted installed release remains A5-r2. No fresh PID, health, model-configuration or token read was performed for this checkpoint.

The NEW tests/installation/context_ai_workstation.py is prepared only (SHA256 ddede711aef497282610cc7109f6190c57569e47076a8471b773b4da4b17c9fa). Its guard tests are tests/test_context_ai_workstation.py (SHA256 c2ebfd91ef0c8ace5e132781be8f43b323f436a4a6dc99e0f6a5880d50866617). Eleven offline tests passed in 0.474 seconds; connector independent static review found no remaining blocker. Historical helpers remain unchanged.

Pending commands are preserved locally under build/workstation/evidence/provider-a6-helper-review/: preflight-command.ps1 is prepared and syntax-checked only; commands.json also holds repair/readchecks templates which require separately reviewed prior-receipt hashes. Do NOT execute them during preservation/publishing.

A6 pins:

- Installer: dist/connections/workstation-a6/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe; 64,359,085 bytes; SHA256 2d87e2bfac18099d9921674a2975604999fc7a79cddf36f5404cd293ff20c2d1.
- Kernel: 6960835b332728672183b2953c4003119ed743a721793dd6e21a7b66181607fc.
- Source content: 886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4.
- SOURCE-MANIFEST file: 110699237a7135eade0906145d7a5e0110300e14165fd7f5de9c955f545df6de.
- App JS: 02f41202e40b8ea85948e3a115e360b74d76ef7abad35b0ee5e1702a90bc9053.
- Extraction receipt: 9f4570cfeab2d46a9d7ba38b18968995016c7185c0671a0011960a08203d9df1.

Publish reviewed source, tests, documentation, lock files and configuration templates. Retain all local evidence/artifacts without deleting or rewriting them, but do not automatically add build/, runtime/, dist/, acquired data, database backups, screenshots, browser profiles, session files, vaults, .env files or real credentials to Git. Existing public sample resources are a separate reviewed source scope; synthetic test keys/tokens are labelled fixtures rather than real credentials. No model weights, local AI executable, signing identity or private workstation configuration belongs in source publication.
