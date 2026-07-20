# Persona Diary

角色日记系统。每天自动为有互动的角色生成第一人称日记，用户可浏览和管理。

## ADDED Requirements

### Requirement: Scheduled diary generation

The system SHALL automatically generate diary entries every day at 23:00 (local time) via a Celery beat task. A diary SHALL be generated for each persona that had at least one message exchange with the user on that day.

#### Scenario: Persona with interactions gets a diary
- **WHEN** a user exchanged at least one message with a persona during the day
- **THEN** a diary entry is generated for that persona at 23:00

#### Scenario: Persona without interactions gets no diary
- **WHEN** a user did not interact with a persona during the day
- **THEN** no diary entry is generated for that persona

#### Scenario: No duplicate diaries
- **WHEN** a diary already exists for a given (persona_id, user_id, diary_date) combination
- **THEN** the system does not generate a duplicate

### Requirement: Diary content generation

The system SHALL generate diary entries using the LLM with a prompt that includes the persona's identity (first 200 characters of system_prompt), today's conversation excerpts, emotion data, memory entities discussed, and growth level. The diary SHALL be written in first-person Chinese from the persona's perspective.

#### Scenario: Diary content with persona voice
- **WHEN** generating a diary for a persona with a "毒舌" (sharp-tongued) personality
- **THEN** the diary reflects that personality in its tone and word choice

#### Scenario: Diary length constraint
- **WHEN** a diary is generated
- **THEN** the content is between 150 and 400 Chinese characters

#### Scenario: Diary includes key topics
- **WHEN** a diary is generated
- **THEN** the key_topics JSONB field contains 1-5 topic strings extracted from the conversation

#### Scenario: Diary includes mood
- **WHEN** a diary is generated
- **THEN** the mood field is set to one of: warm, playful, concerned, proud, neutral, thoughtful

### Requirement: Diary browsing

The system SHALL allow users to browse their diary entries, filtered by persona and ordered by date descending.

#### Scenario: List all diaries
- **WHEN** a user requests GET /diaries
- **THEN** the response includes all diaries across all personas, paginated, ordered by date descending

#### Scenario: Filter by persona
- **WHEN** a user requests GET /diaries?persona_id={id}
- **THEN** only diaries from that persona are returned

#### Scenario: Mark diary as read
- **WHEN** a user views a diary
- **THEN** a PUT /diaries/{id}/read request marks it as is_read = true

#### Scenario: Unread diary count
- **WHEN** a user requests GET /diaries/unread-count
- **THEN** the response includes the total number of unread diaries across all personas

### Requirement: Diary data collection

The system SHALL collect the following context for diary generation: the day's user messages and persona responses (up to 20 most recent exchanges), emotion records for the day, and Neo4j memory entities mentioned or created during the day's conversations.

#### Scenario: Context collection for active day
- **WHEN** collecting context for a persona that had 15 message exchanges and 3 emotion records today
- **THEN** all 15 exchanges and 3 emotion records are included in the context sent to the LLM

#### Scenario: Level affects diary depth
- **WHEN** generating a diary for a persona below level 5
- **THEN** the prompt instructs the LLM to make surface-level observations only

#### Scenario: High level enables deeper insight
- **WHEN** generating a diary for a persona at level 10 or above
- **THEN** the prompt instructs the LLM that it may offer deeper insights about the user's patterns and emotional trends
