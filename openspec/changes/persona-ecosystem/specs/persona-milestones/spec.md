# Persona Milestones

里程碑事件检测与生成系统。在角色与用户的互动过程中，特定条件触发里程碑，LLM 生成故事化描述。

## ADDED Requirements

### Requirement: Milestone detection on interaction

The system SHALL check for milestone eligibility after each interaction round and create milestones when conditions are met. Each milestone type for a given persona-user pair SHALL be unique (no duplicate types with the same occurred_at).

#### Scenario: First meeting milestone
- **WHEN** a persona interacts with a user for the first time (interaction_count goes from 0 to 1)
- **THEN** the system creates a `first_meeting` milestone with an LLM-generated title and description

#### Scenario: Deep talk milestone
- **WHEN** a single conversation exceeds 20 message exchanges
- **THEN** the system creates a `deep_talk` milestone summarizing the conversation's themes

#### Scenario: Memory breakthrough milestone
- **WHEN** the persona recalls and references a memory entity older than 30 days
- **THEN** the system creates a `memory_breakthrough` milestone marking the first "true remembering"

#### Scenario: Emotion peak milestone
- **WHEN** the user sends 3 or more consecutive messages with emotion intensity above 0.7
- **THEN** the system creates an `emotion_peak` milestone noting the user's strong emotional state

#### Scenario: Knowledge milestone
- **WHEN** the same topic (entity cluster) has been discussed 10 or more times
- **THEN** the system creates a `knowledge_milestone` summarizing the user's sustained interest

#### Scenario: Loyalty milestone
- **WHEN** consecutive interaction days reach 7, 30, 100, or 365
- **THEN** the system creates a `loyalty_milestone` with an anniversary-themed description

#### Scenario: Level unlock milestone
- **WHEN** the persona reaches level 5, 10, 15, 20, 25, 30, 40, or 50
- **THEN** the system creates a `level_unlock` milestone reflecting on the relationship's growth

### Requirement: Milestone description generation

The system SHALL generate milestone titles and descriptions using the persona's voice and style. Descriptions SHALL be between 30 and 150 Chinese characters.

#### Scenario: LLM-generated milestone
- **WHEN** a milestone is triggered
- **THEN** the system calls the LLM with a prompt that includes the persona's system_prompt, the milestone type, and relevant context (message excerpts, entity names, emotion data) to generate a personalized title and description

#### Scenario: Milestone references memory entities
- **WHEN** a milestone is related to specific Neo4j entities
- **THEN** the milestone record stores the entity IDs in the memory_entities JSONB column

### Requirement: Milestone list retrieval

The system SHALL expose a list of milestones for each persona-user pair, ordered by occurred_at descending.

#### Scenario: Get milestones
- **WHEN** a user requests GET /personas/{persona_id}/milestones
- **THEN** the response includes an array of milestones with type, title, description, level_at_trigger, and occurred_at
