# Persona Marketplace

角色市场系统。用户可将角色发布到社区市场，其他用户可浏览、搜索、评分和导入角色。

## ADDED Requirements

### Requirement: Publish persona to marketplace

The system SHALL allow a user to publish one of their personas to the marketplace. Publishing creates a listing with a frozen snapshot of the persona's configuration. A persona can only have one active listing at a time.

#### Scenario: First-time publish
- **WHEN** a user publishes a persona with market_name, market_description, tags, and icon
- **THEN** a new MarketListing is created with the persona's full configuration snapshot and is_active = true

#### Scenario: Republish after unpublish
- **WHEN** a user re-publishes a previously unpublished persona
- **THEN** the existing MarketListing is reactivated with updated configuration snapshot

#### Scenario: Cannot publish another user's persona
- **WHEN** a user attempts to publish a persona they do not own
- **THEN** the system returns a 404 error

### Requirement: Marketplace browsing

The system SHALL allow users to browse published personas with filtering, sorting, search, and pagination. Authentication is not required for browsing.

#### Scenario: Browse popular personas
- **WHEN** a user requests GET /personas/marketplace?sort=popular
- **THEN** the response includes listings ordered by downloads descending, 20 per page

#### Scenario: Filter by tags
- **WHEN** a user requests GET /personas/marketplace?tag=情感陪伴&tag=创意写作
- **THEN** only listings matching all specified tags are returned

#### Scenario: Search by keyword
- **WHEN** a user requests GET /personas/marketplace?search=毒舌
- **THEN** only listings whose market_name or market_description contain "毒舌" are returned

#### Scenario: Pagination
- **WHEN** a user requests GET /personas/marketplace?page=2&page_size=20
- **THEN** the response includes the second page of results and total count

### Requirement: Marketplace listing detail

The system SHALL provide detailed view of a marketplace listing including the persona's configuration preview, seller info, rating statistics, and reviews.

#### Scenario: View listing detail
- **WHEN** a user requests GET /personas/marketplace/{listing_id}
- **THEN** the response includes market_name, market_description, tags, icon, rating_avg, rating_count, downloads, version, created_at, seller display info, and persona configuration preview (system_prompt truncated to 300 characters)

#### Scenario: Listing includes reviews
- **WHEN** viewing a listing detail
- **THEN** the response includes the most recent 10 reviews with ratings and comments

### Requirement: Import persona from marketplace

The system SHALL allow an authenticated user to import a marketplace persona into their own persona list. The imported persona starts with fresh growth data. The seller's clone_count is incremented.

#### Scenario: Successful import
- **WHEN** a user imports a marketplace listing
- **THEN** a new AgentPersona is created with the configuration from the persona_snapshot, cloned_from_id is set, and a persona_growth record is created with initial values

#### Scenario: Import increments download count
- **WHEN** a user imports a marketplace listing
- **THEN** the listing's downloads count is incremented by 1
- **THEN** the seller's original persona clone_count is incremented by 1

#### Scenario: Imported persona starts fresh
- **WHEN** a persona is imported from the marketplace
- **THEN** its persona_growth record starts at XP=0, level=1, intimacy=0 regardless of the seller's growth stats

#### Scenario: Cannot import own persona
- **WHEN** a user attempts to import a listing where they are the seller
- **THEN** the system returns an error

### Requirement: Reviews and ratings

The system SHALL allow users who have imported a listing to rate it (1-5 stars) and leave an optional comment. Each user can only review a listing once.

#### Scenario: Submit a review
- **WHEN** a user submits a rating and comment for a listing
- **THEN** the review is created and the listing's rating_avg and rating_count are recalculated

#### Scenario: Update existing review
- **WHEN** a user submits a second review for the same listing
- **THEN** the existing review is updated with the new rating and comment

#### Scenario: Rating average calculation
- **WHEN** a listing has 3 reviews with ratings 5, 4, 3
- **THEN** the rating_avg is 4.00

### Requirement: Unpublish from marketplace

The system SHALL allow the seller to unpublish their listing, making it invisible in the marketplace. Already imported copies are unaffected.

#### Scenario: Unpublish
- **WHEN** the seller requests POST /personas/marketplace/{listing_id}/unpublish
- **THEN** the listing's is_active is set to false

#### Scenario: Unpublished listing not visible
- **WHEN** a listing is unpublished
- **THEN** it does not appear in marketplace browsing results

### Requirement: Marketplace persona configuration snapshot

The system SHALL freeze the persona's configuration at publish time as a JSONB snapshot. Subsequent edits to the original persona do not affect the marketplace listing until the seller explicitly updates it.

#### Scenario: Snapshot captures full config
- **WHEN** a persona is published
- **THEN** the persona_snapshot contains: system_prompt, temperature, tool_keys, enable_knowledge, enable_memory, enable_web_search, enable_mcp, mcp_server_ids, enable_active_recall, enable_cross_session, kb_ids, conversation_scope, context_window, human_mode, show_avatar, allow_agent_call

#### Scenario: Original edits don't affect listing
- **WHEN** a seller modifies their persona's system_prompt after publishing
- **THEN** the marketplace listing still shows the original snapshot until the seller explicitly updates the listing
