# Remote iOS Deploy Skill

[English](README.md) | 简体中文

把 Mac 上的 iOS 开发部署延伸到远程 iPhone：本地 Bonjour 代理发现 + TCP/UDP 桥接，配合构建、签名检查与持续启动验证。适用于 Codex 等支持 `SKILL.md` 的 coding agents。

## 已验证的边界

- 手机在两个不同的 Wi-Fi 场景中，通过 VPN/overlay 网络从远程 Mac 安装成功；安装命令没有移到手机附近的 Mac。
- 手机纯蜂窝、VPN/overlay 客户端显示在线时，开发入口拒绝连接，**直接部署未通过**。
- 切回另一 Wi-Fi 后，原配置恢复，重试安装成功；不承诺无缝漫游。
- IPA 网页安装仅验证过导出、签名、HTTPS 下载，手机端纯蜂窝安装仍待验证。
- 每台部署 Mac 需要自己的配对信任与签名环境；不能只复制配置或另一台 Mac 的配对记录。

这里没有个人设备地址、UDID、签名私钥、原始日志或签名安装包。硬件实测与本仓库通用脚本的本地测试分开记录，详见 [验证记录](references/validation.md)。

本 skill 不绑定某个 VPN 产品；网络必须能让 Mac 通过系统 TCP/UDP socket 访问手机开发服务。使用通用配置不代表所有 VPN、系统版本或网络条件都已经验证。

## 新手机／新电脑：最低操作要求

关键是**这台 Mac 与这部手机之间有有效的配对信任**，不是“以前插过线”就够了。首次使用按以下流程准备：

1. **Mac 操作者，每台部署电脑准备一次：**安装兼容手机系统的 Xcode、Python 3 和 `socat`；配置项目所属团队的签名证书及私钥、包含手机 UDID 的描述文件；配置能打通所需 TCP/UDP 的 VPN/overlay。
2. **手机持有人，每组 Mac–手机首次配对一次：**用数据线把已解锁手机接到准备部署的 Mac；按提示点“信任”并输入锁屏密码，在 Xcode 完成配对。如果尚未开启开发者模式，到“设置 → 隐私与安全 → 开发者模式”开启，重启后再次确认。如果没有这个选项，先在 Xcode 发起配对。参见 [Apple 配对说明](https://help.apple.com/xcode/mac/current/en.lproj/devbc48d1bad.html)及 [开发者模式说明](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)。
3. **Agent／Mac 操作者：**采集真实 Bonjour 身份和开发服务地址，填写桥接配置并检查签名。建议手机离开前，拔线完成同 Wi-Fi 安装启动，再做一次异网验证；这是验收建议，不是额外的信任授权步骤。
4. **以后每次部署：**手机连接 Wi-Fi，VPN/overlay 能让 Mac 访问手机开发服务；需要时解锁或确认系统提示。已验证的桥接流程不要求手机附近另有一台安装用 Mac。重置信任、地址或发现信息变化后可能需要重新处理，不承诺永远零操作。

| 手机当前状态 | 最低需要做什么 |
|---|---|
| 已与当前 Mac 有效配对 | 复用配对，检查签名、发现信息和网络；不因使用本 skill 再插一次线。 |
| 只与另一台 Mac 配过对 | 给准备部署的新 Mac 单独配对一次；同一个 Apple ID、复制配置均不能代替。 |
| 已在远处，从未与当前 Mac 配对 | 本方案没有验证过远程首次配对；需安排首次配对，或明确改用其他安装 Mac／合适的分发方式。 |
| 只有蜂窝网络 | 实测直装失败；网页安装需另行同意并完成手机端验证。 |

**人工操作的底线：**首次配对时，需要有人拿着手机接线、解锁、确认信任，以及按需开启开发者模式并重启确认；脚本不能代点这些安全提示。Mac 工具安装、配置整理、构建、桥接和部署检查可交给 agent。

如果手机完全不能接触部署 Mac，可以另选安装 Mac（改变部署端），或评估免 Xcode 配对的 Ad Hoc／TestFlight 等分发方式；它们需要对应的开发者账号、签名或分发流程，不属于已验证的远程直装路径，也不会自动发布。**开发签名 IPA 网页安装仍涉及开发者模式，不能当作全新手机免配对的捷径。**详细分支见 [首次准备指南（英文）](references/first-time-setup.md)。

## 安装与使用

目标目录不存在时：

```bash
git clone https://github.com/CodeEagle/remote-ios-deploy-skill.git ~/.codex/skills/remote-ios-deploy
```

若目录已存在，先检查其内容，不要覆盖已有修改。让 agent 重新加载技能后使用：

> 使用 $remote-ios-deploy，从这台 Mac 部署当前项目到远程 iPhone，验证桥接路径与启动结果。

入口：[SKILL.md](SKILL.md)。详细操作：[跨网络直装](references/direct.md)、[可选网页分发](references/web-distribution.md)。脚本需要 Python 3；桥接还需要 macOS `dns-sd` 和 `socat`，安装需要兼容的 Xcode 与正确签名。

```bash
python3 scripts/bridge.py --help
python3 scripts/build_deploy.py --help
python3 -m unittest discover -s tests -v
```

默认桥接范围会启动约 1006 个 socat 进程，适合验证而非资源优化。端口范围、地址和 Bonjour 数据需要按设备实测配置；脚本不会自动配置 VPN、配对、证书、防火墙或开机自启。仅在可信网络开放监听，测试结束及时停桥。

## 来源

协议桥接思路参考 [Kevin Paterson 的原始实测](https://dev.to/kvnpt/how-to-remotely-iterate-deploy-your-sideloaded-ios-apps-over-tailnet-jak)，并结合本项目记录的 iOS 27 跨网络部署实测修正边界。本文没有复制该文的脚本；仓库提供独立实现的进程管理和部署验证辅助程序。
