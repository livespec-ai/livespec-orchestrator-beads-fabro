#!/usr/bin/env python3
"""Shebang wrapper for publication_broker. No logic; see livespec_orchestrator_beads_fabro.commands.publication_broker."""

from _bootstrap import bootstrap

# The broker reads its own credential from a file it is handed by argv, so the
# self-heal chokepoint demands no environment secret of it.
bootstrap(required=())

from livespec_orchestrator_beads_fabro.commands.publication_broker import main

raise SystemExit(main())
