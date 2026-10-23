"""The strategy manifest contract used for ZIP validation and API responses."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParameterBase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1)
    required: bool = Field(strict=True)


class IntegerParameter(ParameterBase):
    type: Literal['integer']
    default: int = Field(default_factory=lambda: None, strict=True)
    min: float = Field(default_factory=lambda: None, strict=True)
    max: float = Field(default_factory=lambda: None, strict=True)


class NumberParameter(ParameterBase):
    type: Literal['number']
    default: float = Field(default_factory=lambda: None, strict=True)
    min: float = Field(default_factory=lambda: None, strict=True)
    max: float = Field(default_factory=lambda: None, strict=True)


class BooleanParameter(ParameterBase):
    type: Literal['boolean']
    default: bool = Field(default_factory=lambda: None, strict=True)


class StringParameter(ParameterBase):
    type: Literal['string']
    default: str = Field(default_factory=lambda: None)


class EnumParameter(ParameterBase):
    type: Literal['enum']
    default: str = Field(default_factory=lambda: None)
    options: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, json_schema_extra={'uniqueItems': True})


Parameter = Annotated[IntegerParameter | NumberParameter | BooleanParameter | StringParameter | EnumParameter, Field(discriminator='type')]


class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1]
    interface_version: Literal[1]
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    markets: list[Literal['CN', 'US']] = Field(min_length=1, json_schema_extra={'uniqueItems': True})
    bar_interval: str = Field(pattern=r'^[1-9][0-9]*m$')
    required_fields: list[Literal['open', 'high', 'low', 'close', 'volume']] = Field(min_length=1, json_schema_extra={'uniqueItems': True})
    entrypoint: Literal['strategy:on_bar']
    python: Literal['3.13']
    dependencies: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(json_schema_extra={'uniqueItems': True})
    parameters: list[Parameter]

    @model_validator(mode='after')
    def check_rules(self):
        if not self.name.strip() or not self.description.strip():
            raise ValueError('策略名称和说明不能为空')
        if len(set(self.markets)) != len(self.markets) or len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError('市场或行情字段不能重复')
        if len(set(self.dependencies)) != len(self.dependencies) or any(not x or len(x) > 200 for x in self.dependencies):
            raise ValueError('依赖声明无效或重复')
        seen = set()
        for param in self.parameters:
            name = param.name.strip()
            if not name or name.casefold() in seen:
                raise ValueError('参数名称为空或重复')
            seen.add(name.casefold())
            if any(secret in name.casefold() for secret in ('password', 'secret', 'token', 'api_key', 'credential', '密码', '密钥')):
                raise ValueError('策略参数不能保存密码或密钥')
            if 'default' in param.model_fields_set and param.default is None:
                raise ValueError(f'参数 {name} 的默认值类型无效')
            if isinstance(param, EnumParameter):
                if len(set(param.options)) != len(param.options) or any(not option.strip() for option in param.options):
                    raise ValueError(f'参数 {name} 缺少有效枚举选项')
                if param.default is not None and param.default not in param.options:
                    raise ValueError(f'参数 {name} 的默认值不在选项中')
            if isinstance(param, (IntegerParameter, NumberParameter)):
                if any(value is not None and not math.isfinite(value) for value in (param.default, param.min, param.max)):
                    raise ValueError(f'参数 {name} 须使用有限数字')
                if param.min is not None and param.max is not None and param.min > param.max:
                    raise ValueError(f'参数 {name} 的范围无效')
                if param.default is not None and param.min is not None and param.default < param.min:
                    raise ValueError(f'参数 {name} 的默认值小于下限')
                if param.default is not None and param.max is not None and param.default > param.max:
                    raise ValueError(f'参数 {name} 的默认值大于上限')
        return self
