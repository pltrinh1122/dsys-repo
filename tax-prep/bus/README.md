# Message bus → dsys-store

Broadcast messages do NOT accrete here. They accrete to the separate
**dsys-store** repo (`https://github.com/pltrinh1122/dsys-store`),
under `bus/<topic>/`.

Two-repo topology: dsys-repo is software (code, specs, tests);
dsys-store is the append-only accretion medium for session broadcast
messages. This directory keeps no message files — it exists only so
the pointer is discoverable.

On a new machine:

    git clone https://github.com/pltrinh1122/dsys-store ~/workspace/dsys-store

then `taxprep bus whoami` to confirm the resolved store dir.
`taxprep config set store_dir <path>` (or `TAXPREP_STORE_DIR`) moves it.

See `../COLLABORATION.md` ("The bus replaces hand-carried prompts").
