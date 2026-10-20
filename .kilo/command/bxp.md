# BXP Protocol Commands

Commands for working with the BXP Protocol repository.

## validate-bxp

Validate a .bxp.json or .bxp file against the v2.0 spec.

Usage: `/validate-bxp <path>`

Example: `/validate-bxp datasets/sample_readings.bxp.json`

## run-conformance

Run the conformance test suite (Python + TypeScript).

Usage: `/run-conformance`

## start-server

Start the BXP reference server locally.

Usage: `/start-server`

## generate-reading

Generate a sample BXP reading.

Usage: `/generate-reading <city> <pm25> <no2>`

Example: `/generate-reading Accra 47.2 18.3`
