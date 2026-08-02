## ADDED Requirements

### Requirement: Message list uses virtual scrolling

The system SHALL render only the messages currently visible in the viewport plus a configurable overscan buffer, instead of mounting all messages as DOM nodes.

#### Scenario: Large message list renders efficiently

- **WHEN** a conversation contains 200+ messages
- **THEN** the browser SHALL mount no more than 30 message DOM nodes (viewport ~15 + buffer ~15)
- **AND** scrolling through the list SHALL maintain 60fps with no perceptible jank

#### Scenario: Scrolling to top loads historical messages

- **WHEN** user scrolls to the top of the visible message list
- **THEN** messages above the viewport SHALL become visible without full-page reload
- **AND** previously visible messages below the viewport SHALL be unmounted

### Requirement: Streaming messages update height automatically

The system SHALL automatically adjust list item height when streaming content causes the message element to grow.

#### Scenario: Token appending increases message height

- **WHEN** an AI message is streaming and new tokens are appended to its content
- **THEN** the virtual list SHALL remeasure the item's new height within one animation frame
- **AND** the scroll position SHALL adjust to keep the bottom of the message visible

#### Scenario: Tool call chips expand message height

- **WHEN** user expands a collapsed tool call chip section within a message
- **THEN** the virtual list SHALL remeasure the item and adjust layout accordingly

### Requirement: Auto-scroll follows new content

The system SHALL automatically scroll to the bottom when new messages arrive, unless the user has manually scrolled up.

#### Scenario: Auto-scroll to bottom on new message

- **WHEN** a new message is added to the list
- **AND** the user is currently scrolled to (or near) the bottom of the list (within 100px threshold)
- **THEN** the list SHALL smoothly scroll to show the new message

#### Scenario: Pause auto-scroll when user scrolls up

- **WHEN** user manually scrolls upward more than 100px from the bottom
- **THEN** auto-scroll SHALL be disabled
- **AND** new messages SHALL NOT cause automatic scrolling

#### Scenario: Resume auto-scroll when user returns to bottom

- **WHEN** user manually scrolls back within 100px of the bottom
- **THEN** auto-scroll SHALL resume for subsequent new messages

### Requirement: Shared virtual list component

The system SHALL provide a shared `VirtualMessageList` component that both ChatPage and GroupChatPage use, accepting `messages` array and `renderItem` function as props.

#### Scenario: ChatPage uses VirtualMessageList

- **WHEN** ChatPage mounts a conversation
- **THEN** the message list SHALL use `VirtualMessageList` for rendering
- **AND** the user SHALL perceive no visual difference from the previous implementation

#### Scenario: GroupChatPage uses VirtualMessageList

- **WHEN** GroupChatPage mounts a group conversation
- **THEN** the message list SHALL use `VirtualMessageList` for rendering
- **AND** task plan cards SHALL render correctly within the virtual list
