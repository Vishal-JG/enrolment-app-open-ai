# MCP Tool Review

## Risk Identified

The `project_files` tool could expose sensitive paths outside the application workspace.

## Correction Applied

Added path validation to `tools.py`.

The `project_files` tool now resolves the requested path and verifies that it is contained within the application directory before accessing it.

Paths outside the application directory are rejected.

## Retest

The MCP implementation was re-tested after the path validation was added.

Valid application paths remain accessible, while paths outside the application directory are rejected.