## ADDED Requirements

### Requirement: Skill script execution increments call count

When a skill's script is executed via `skill__xxx` tool or `bash` tool, the system SHALL increment the skill's call count and record success/failure.

#### Scenario: skill__xxx tool increments counter

- **WHEN** an Agent invokes a `skill__xxx` tool that runs a script
- **THEN** the skill's `call_count` SHALL increase by 1
- **AND** `last_called_at` SHALL update to current time

#### Scenario: bash tool with matched skill increments counter

- **WHEN** an Agent invokes `bash` to execute a script
- **AND** the script path matches a skill's storage directory
- **THEN** the matched skill's `call_count` SHALL increase by 1
- **AND** if the script exits with code 0, `success_count` SHALL increase by 1
- **AND** if the script exits with non-zero code, `error_count` SHALL increase by 1

#### Scenario: bash without matching skill does not crash

- **WHEN** an Agent invokes `bash` to execute a script
- **AND** the script path does not match any skill directory
- **THEN** no skill counter SHALL be modified
- **AND** the bash execution SHALL proceed normally

### Requirement: Skill call statistics visible in persona edit view

The system SHALL display per-skill call statistics in the persona edit modal's skill list.

#### Scenario: Skill with calls shows statistics

- **WHEN** a persona has a skill with `call_count > 0`
- **THEN** the skill row SHALL display total calls, success count, and error count
- **AND** SHALL display relative time since last call (e.g. "2小时前")

#### Scenario: Skill without calls shows no statistics

- **WHEN** a persona has a skill with `call_count == 0`
- **THEN** the skill row SHALL NOT display call statistics
