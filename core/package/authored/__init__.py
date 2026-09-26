"""Loop-authored agent profiles (DR-CMD-083).

Each module here is authored through the author-agent loop
(core/package/author_agent.py): commission -> author -> stage -> drive ->
diagnose, with bytes hash-pinned in the authoring manifest. Modules use
ABSOLUTE imports so the factory driver can load them from any harness
root. Nothing here is hand-placed past the driver.
"""
