from dataclasses import dataclass, field


@dataclass
class TriggerDefinition:
    id: str
    name: str
    description: str
    config_schema: dict = field(default_factory=dict)


@dataclass
class ActionDefinition:
    id: str
    name: str
    description: str
    config_schema: dict = field(default_factory=dict)


@dataclass
class Connector:
    id: str
    name: str
    description: str
    triggers: list[TriggerDefinition] = field(default_factory=list)
    actions: list[ActionDefinition] = field(default_factory=list)
    connection_schema: dict = field(default_factory=dict)
