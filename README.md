# Remote iOS Deploy Skill

把 Mac 上的 iOS 开发部署延伸到远程 iPhone：本地 Bonjour 代理发现 + TCP/UDP 桥接，配合构建、签名检查与持续启动验证。适用于 Codex 等支持 `SKILL.md` 的 coding agents。

## 已验证的边界

- 手机在两个不同的 Wi-Fi 场景中，通过 VPN/overlay 网络从远程 Mac 安装成功；安装命令没有移到手机附近的 Mac。
- 手机纯蜂窝、VPN/overlay 客户端显示在线时，开发入口拒绝连接，**直接部署未通过**。
- 切回另一 Wi-Fi 后，原配置恢复，重试安装成功；不承诺无缝漫游。
- IPA 网页安装仅验证过导出、签名、HTTPS 下载，手机端纯蜂窝安装仍待验证。
- 每台部署 Mac 需要自己的配对信任与签名环境；不能只复制配置或另一台 Mac 的配对记录。

这里没有个人设备地址、UDID、签名私钥、原始日志或签名安装包。硬件实测与本仓库通用脚本的本地测试分开记录，详见 [验证记录](references/validation.md)。

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
