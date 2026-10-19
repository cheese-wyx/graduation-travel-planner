# 旅伴 Go：毕业旅行拼团规划

Python + Streamlit + SQLite 演示项目。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 在线部署

1. 在 GitHub 创建公开仓库，上传 `app.py`、`requirements.txt`。
2. 打开 https://share.streamlit.io/ ，用 GitHub 登录。
3. 选择仓库、分支及入口文件 `app.py`，点击 Deploy。
4. 复制生成的 `https://...streamlit.app` 地址作为提交链接。
5. 保持仓库、应用和访问权限为公开，部署后用无痕窗口验证。
6. 更新代码时继续使用原仓库和原应用，不要删除并重新创建应用，以尽量保持域名不变。

## 限制

- SQLite 数据在 Streamlit Community Cloud 上可能因重启、重新部署而丢失；正式使用应迁移到 Supabase/PostgreSQL 等持久化数据库。
- 未实现身份认证和访问隔离，不能用于存储真实个人隐私、支付信息。
- 行程是规则生成，不代表真实地图路线和开放时间。
- 仅作课程/面试演示，不支持真实交易。
