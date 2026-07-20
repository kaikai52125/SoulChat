# Persona Traits

可解锁特质系统。角色随等级提升解锁新行为特质，特质通过注入 system prompt 改变角色的对话风格和能力。

## ADDED Requirements

### Requirement: Trait unlock by level

The system SHALL unlock specific traits when a persona reaches the required level. Unlocked traits are stored in persona_growth.unlocked_traits as a JSONB array of trait keys.

#### Scenario: Memory savant at Lv.5
- **WHEN** a persona reaches level 5
- **THEN** the `memory_savant` trait is added to unlocked_traits

#### Scenario: Humor unlock at Lv.8
- **WHEN** a persona reaches level 8
- **THEN** the `humor_unlock` trait is added to unlocked_traits

#### Scenario: Emotion aware at Lv.10
- **WHEN** a persona reaches level 10
- **THEN** the `emotion_aware` trait is added to unlocked_traits

#### Scenario: Style mirror at Lv.12
- **WHEN** a persona reaches level 12
- **THEN** the `style_mirror` trait is added to unlocked_traits

#### Scenario: Proactive care at Lv.15
- **WHEN** a persona reaches level 15
- **THEN** the `proactive_care` trait is added to unlocked_traits

#### Scenario: Deep insight at Lv.20
- **WHEN** a persona reaches level 20
- **THEN** the `deep_insight` trait is added to unlocked_traits

#### Scenario: Memory guardian at Lv.25
- **WHEN** a persona reaches level 25
- **THEN** the `memory_guardian` trait is added to unlocked_traits

### Requirement: Trait prompt injection

The system SHALL inject trait-specific instructions into the persona's system prompt at conversation time. Each unlocked trait contributes a short instruction block that modifies the persona's behavior.

#### Scenario: Single trait injection
- **WHEN** a persona has the `emotion_aware` trait unlocked
- **THEN** the system prompt includes an instruction about perceiving and responding to the user's emotional state

#### Scenario: Multiple trait injection
- **WHEN** a persona has both `memory_savant` and `proactive_care` traits unlocked
- **THEN** both trait instruction blocks are appended to the system prompt, separated by newlines

#### Scenario: No traits unlocked
- **WHEN** a persona has no unlocked traits (level 1-4 for most traits)
- **THEN** no trait instructions are injected into the system prompt

### Requirement: Trait configuration

The system SHALL define each trait's name, description, required level, and injectable prompt instruction in a centralized configuration.

#### Scenario: Trait definition structure
- **WHEN** a developer adds a new trait
- **THEN** they add an entry to the trait configuration specifying the trait key, display name, required level, and prompt instruction template
