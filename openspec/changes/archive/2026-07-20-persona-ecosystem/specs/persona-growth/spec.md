# Persona Growth

角色成长数值追踪系统。每次用户与角色对话互动后，系统自动记录 XP、更新等级和亲密度。

## ADDED Requirements

### Requirement: XP accumulation on interaction

The system SHALL award XP to a persona-user pair after each message exchange round. XP is calculated based on the interaction context including conversation depth, memory reuse, tool usage, and emotional feedback.

#### Scenario: Basic interaction earns base XP
- **WHEN** a user sends a message and the persona responds
- **THEN** the system awards 10 base XP to the persona-user growth record

#### Scenario: Deep conversation bonus
- **WHEN** the current conversation exceeds 5 turns
- **THEN** each subsequent turn awards an additional 5 XP

#### Scenario: Memory reuse bonus
- **WHEN** the persona references a memory entity older than 30 days in its response
- **THEN** the system awards an additional 3 XP

#### Scenario: Tool usage bonus
- **WHEN** the persona invokes at least one tool (knowledge base, web search, or MCP) during the response
- **THEN** the system awards an additional 2 XP

#### Scenario: Positive emotion feedback bonus
- **WHEN** the user's next message after a response has an emotional valence greater than 0.6
- **THEN** the system awards an additional 5 XP

#### Scenario: Daily XP cap
- **WHEN** a persona-user pair has already earned 200 XP in the current calendar day
- **THEN** no further XP is awarded for that pair until the next day

### Requirement: Level progression

The system SHALL calculate the persona's level based on cumulative XP using a progressive threshold curve. The level SHALL be an integer from 1 to 50.

#### Scenario: Initial level
- **WHEN** a persona-user growth record is first created
- **THEN** the level is 1 and XP is 0

#### Scenario: Level up at threshold
- **WHEN** cumulative XP reaches or exceeds the threshold for the next level
- **THEN** the level is incremented and a level-up milestone event is triggered

#### Scenario: XP threshold scaling
- **WHEN** the persona reaches higher levels
- **THEN** the XP required for each subsequent level increases (e.g., Lv.2 requires 100 XP, Lv.10 requires 5000 XP, Lv.50 requires 500,000 XP)

### Requirement: Intimacy calculation

The system SHALL compute an intimacy score (0–100) based on level, consecutive interaction days, milestone count, and average emotional valence.

#### Scenario: New relationship
- **WHEN** a persona and user have just started interacting
- **THEN** the intimacy score is 0

#### Scenario: Long-term relationship
- **WHEN** a persona has reached Lv.20 with 30+ consecutive days, 10+ milestones, and positive emotional history
- **THEN** the intimacy score is above 60

### Requirement: Consecutive days tracking

The system SHALL track consecutive days of interaction between a persona and user. A day counts as "interacted" if at least one message exchange occurred.

#### Scenario: Streak continues
- **WHEN** the user interacts with the persona on consecutive calendar days
- **THEN** the consecutive_days counter increments

#### Scenario: Streak breaks
- **WHEN** the user does not interact with the persona for a full calendar day
- **THEN** the consecutive_days counter resets to 0

#### Scenario: Streak milestone bonus
- **WHEN** the consecutive_days reaches 7
- **THEN** the system awards a bonus 10 XP

### Requirement: Growth data retrieval

The system SHALL expose growth state for each persona-user pair via the API.

#### Scenario: Get growth for active persona
- **WHEN** a user requests GET /personas/{persona_id}/growth
- **THEN** the response includes xp, level, intimacy, interaction_count, consecutive_days, unlocked_traits, and progress to next level
