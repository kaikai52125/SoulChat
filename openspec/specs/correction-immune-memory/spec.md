# correction-immune-memory

## Purpose

Memory conflict resolution capability: 

## ADDED Requirements

### Requirement: CorrectionRecord node created on human correction

当用户对实体执行 confirm、correct 或 delete 操作时，系统 SHALL 在 Neo4j 中创建一个 `CorrectionRecord` 节点，记录被操作的实体名（规范化小写）、实体类型、操作类型和操作时间。

#### Scenario: Confirm creates record
- **WHEN** 用户确认实体 (name="用户", type="生命体")
- **THEN** Neo4j 中创建 CorrectionRecord {entity_name: "用户", entity_type: "生命体", action: "confirm"}

#### Scenario: Correct creates record with corrected name
- **WHEN** 用户将实体 (name="字节", type="组织") 修正为 (name="字节跳动", type="组织")
- **THEN** Neo4j 中创建 CorrectionRecord {entity_name: "字节", entity_type: "组织", action: "correct", corrected_to: "字节跳动"}

#### Scenario: Delete creates record
- **WHEN** 用户删除实体 (name="临时项目", type="具体目标")
- **THEN** Neo4j 中创建 CorrectionRecord {entity_name: "临时项目", entity_type: "具体目标", action: "delete"}

### Requirement: Extraction pipeline checks CorrectionRecord

萃取管线的实体去重步骤 SHALL 在创建新实体前查询 CorrectionRecord。若存在匹配记录则按规则处理。

#### Scenario: Deleted entity not re-created
- **WHEN** 新萃取想要创建实体 (name="临时项目", type="具体目标")，且存在 matching action="delete" 的 CorrectionRecord
- **THEN** 该实体被跳过，不写入图谱

#### Scenario: Corrected entity auto-renamed
- **WHEN** 新萃取想要创建实体 (name="字节", type="组织")，且存在 matching action="correct" 的 CorrectionRecord (corrected_to="字节跳动")
- **THEN** 实体 name 自动设为 "字节跳动"

#### Scenario: Confirmed entity passes through
- **WHEN** 新萃取创建实体 (name="用户", type="生命体")，存在 matching action="confirm" 的 CorrectionRecord
- **THEN** 实体正常处理，不受阻止
