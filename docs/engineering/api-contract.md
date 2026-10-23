# 前后端 HTTP 接口协议规范

## 结论

管理接口以 **FastAPI 路由和 Pydantic 模型**为唯一来源。FastAPI 导出 OpenAPI，`openapi-typescript` 据此生成 TypeScript 类型，前端使用 `openapi-fetch` 发请求。不要手写或维护第二份 OpenAPI JSON、接口路径表和响应类型。

```text
FastAPI 路由 + Pydantic 模型
           ↓ 导出
        OpenAPI
           ↓ openapi-typescript
   web/infra/openapi.d.ts
           ↓ openapi-fetch
        前端请求
```

## 改接口时怎么做

1. 在 `backend/app/api.py` 定义路由、请求参数、状态码和响应模型；在 `backend/app/transport.py` 或所属模块定义 Pydantic 模型。业务规则仍由业务模块决定。
2. 让 OpenAPI 如实描述前端需要的内容：必填请求头、表单文件、成功与常见错误响应、二进制下载等。不要只在中间件或返回代码里实现，却让协议缺失。
3. 从仓库根目录运行 `npm run generate:api --prefix web`，更新 `web/infra/openapi.d.ts`。该文件是生成物，随接口改动一同提交，不手工编辑。
4. 在 `web/infra/api.ts` 使用 `openapi-fetch` 和生成的 `paths` 调用接口；页面从生成类型取得数据类型。需要编码 `FormData` 或读取 `Blob` 时，在请求边界处理，不另写一套接口模型。
5. 运行下列检查，并对变更的请求做实际联调。类型检查能发现路径、字段和类型漂移，但不能证明运行时数据与业务行为正确。

```sh
npm run check:api --prefix web
npm run build --prefix web
.venv/bin/python -m pytest -q
```

本机生成脚本默认使用仓库的 `.venv/bin/python`；使用其他 Python 环境时设置 `LIGHTNING_PYTHON`。`check:api` 会从当前后端重新导出协议，并比较已提交的生成文件。容器构建也会从当前后端重新生成类型，再构建页面。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `scripts/export_openapi.py` | 从当前 FastAPI 应用导出 OpenAPI；不连接数据库。 |
| `web/scripts/generate_api_types.mjs` | 调用 `openapi-typescript` 生成或检查 TypeScript 声明。 |
| `web/infra/openapi.d.ts` | 生成的接口类型，禁止手改。 |
| `web/infra/api.ts` | 基于 `openapi-fetch` 的实际请求及上传、下载等传输处理。 |
| `deploy/Dockerfile` | 构建时导出当前协议、生成前端类型并构建页面。 |

策略包的 `strategy.json` 是另一份合同，不属于 HTTP OpenAPI。其模型与发布的 JSON Schema 的关系按对应技术方案维护。
