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
- Cookie 属于敏感登录凭据，不要粘贴到聊天、Issue 或 Actions 日志中。
- 代码推送只运行离线模拟测试，不会发送真实签到请求。
- 主任务在北京时间 12:17–12:37 的有界随机窗口内执行；18:43–19:03 的备用窗口仅在当天主任务未成功时启用。
- 执行前先用状态接口验证 Cookie，认证失败时不会发送签到请求。

3. 手机推送（非必须）

- 添加1个`repository secret`，命名为`SENDKEY`，其值对应 PushDeer key: ([获取地址](https://www.pushdeer.com/product.html))。

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
