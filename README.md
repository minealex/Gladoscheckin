# Glados自动签到

## 食用方式：

### 注册一个GLaDOS的账号([注册地址](https://glados.space/landing/0A58E-NV28S-6U3QV-33VMG))

#### 我的邀请码：([0A58E-NV28S-6U3QV-33VMG](https://0a58e-nv28s-6u3qv-33vmg.glados.space)) 

### **Fork**本仓库

![图片加载失败](imgs/1.png)

### 添加**secret**

1. 跳转至自己的仓库的`Settings`->`Secrets and variables`->`Action`

2. 添加一个 `repository secret`，名称使用 `COOKIE` 或 `COOKIES`，值只填写从 `glados.cloud` 复制的 Cookie。两种名称均兼容；如果同时存在，优先使用 `COOKIE`。

- 在GLaDOS的签到页面按`F12`

- 切换到`Network`页面下，刷新

![图片加载失败](imgs/2.png)

- 点击第一个选项卡后在`Request Headers`下找到`Cookie`，右键复制cookie的值即可

  > 参考格式：koa:sess=eyJ1c2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxAwMH0=; koa:sess.sig=xJkOxxxxxxxxxxxxxxxtnM;

![图片加载失败](imgs/3.png)

- Cookie 必须放在同一行，键值之间使用分号和空格；不要使用 `&` 拼接多个账号。
- **Cookie 必须包含 `gld:sess` 和 `gld:sess.sig`**：GLaDOS 于 2026-09 前后把登录会话从 `koa:sess` 迁到了 `gld:sess`，只复制旧的 `koa:sess` 会被服务端拒绝（返回「没有权限」）。最稳妥的做法是把 Request Headers 里的 Cookie **整行**复制下来。
- Cookie 属于敏感登录凭据，不要粘贴到聊天、Issue 或 Actions 日志中。
- 代码推送只运行离线模拟测试，不会发送真实签到请求。
- 主任务在北京时间 12:17–12:37 的有界随机窗口内执行；18:43–19:03 的备用窗口仅在当天主任务未成功时启用。
- 执行前先用状态接口验证 Cookie，认证失败时不会发送签到请求。

3. 手机推送（非必须）

- 添加1个`repository secret`，命名为`SENDKEY`，其值对应 PushDeer key: ([获取地址](https://www.pushdeer.com/product.html))。
- 配置后，签到成功与失败都会推送到手机；推送失败不会影响签到本身。

### 故障排查（签到失败时先看这里）

打开失败的 Actions 运行记录，展开 `production check-in` → `Run check-in`，脚本会打印三行诊断信息：

```text
Cookie 来源：COOKIE | 长度 213 字符 | 字段 koa:sess,koa:sess.sig | 指纹 3f9c1a02
Cookie 有效期：会话有效期至 2026-10-24 09:12，剩余 24.3 天
GLaDOS 签到失败：认证失败：没有权限（Cookie 无效或已过期；...）
```

常见原因与处理方式：

| 日志关键字 | 原因 | 处理 |
| --- | --- | --- |
| `认证失败` / `没有权限` | Cookie 里缺少 `gld:sess`（最常见）或会话已作废 | 重新登录 [glados.cloud](https://glados.cloud)，**整行复制** Cookie（须含 `gld:sess` 与 `gld:sess.sig`），更新 Secret |
| `未配置 Cookie Secret` | Secret 名称不对或值被清空 | Secret 名称必须是 `COOKIE` 或 `COOKIES` |
| `Cookie 必须是单行` | 复制时带上了换行 | 粘贴前先压成一行，键值之间用 `; ` 分隔 |
| `状态请求失败` | 站点临时不可用或网络抖动 | 只读请求会自动重试 3 次；仍失败则等当天 18:43 的备用窗口 |
| `签到请求失败` | 签到接口异常 | 脚本不会重试签到请求（避免重复签到），等备用窗口重试 |

- Cookie 剩余有效期不足 7 天时，运行记录里会出现黄色 `::warning::`；已过期时出现红色 `::error::`，可直接据此提前续期。
- 诊断信息只输出 Cookie 的长度、字段名和哈希指纹，不会打印 Cookie 内容，可放心贴在日志里。

### **star**自己的仓库

![图片加载失败](imgs/4.png)

## 文件结构

```shell
│  checkin.py	# 签到脚本
│
├─.github
│  └─workflows
│          gladosCheck.yml	# Actions 配置文件
```

## 声明

本项目不保证稳定运行与更新, 因GitHub相关规定可能会删库, 请注意备份
