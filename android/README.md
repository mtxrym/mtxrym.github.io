# AI Coding 资讯 · Android App

原生 Android 客户端（Kotlin + Jetpack Compose + Material 3），数据直接读取本仓库发布到 GitHub 的文件：

| 文件 | 内容 |
| --- | --- |
| `blog.json` | 精选条目（标题、摘要、作者、主题标签、得分构成、HF 点赞、代码仓库…） |
| `data/status.json` | 数据源健康状态 + 当前生效的更新策略 |
| GitHub Actions API | “Update AI Coding Feed” 最近一次运行结果 |

读取顺序：GitHub Pages → raw.githubusercontent.com → jsDelivr CDN，任一可用即可；成功后缓存到本机，离线时显示缓存。

## 功能

- 下拉刷新、离线缓存、网络失败自动切换镜像
- 搜索（标题 / 摘要 / 作者 / 主题）、类别与来源筛选、按得分 / 时间 / 热度排序
- 收藏（与网页使用相同的 id 规则）、紧凑视图
- 摘要展开、主题标签一键搜索、HF 点赞与代码仓库直达
- 顶栏健康徽标（正常 / 部分异常 / 更新滞后 / 抓取失败），点开查看数据源、策略与 GitHub Actions 运行状态
- 跟随系统深色模式，Android 12+ 使用 Material You 动态取色

## 下载安装

推送到默认分支后，`.github/workflows/android.yml` 会自动构建并发布到
[Releases](https://github.com/mtxrym/mtxrym.github.io/releases/latest)，下载 `ai-coding-feed.apk` 安装即可（Android 8.0+）。

## 本地构建

需要 JDK 17+ 与 Android SDK（platform 36）：

```bash
cd android
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew testDebugUnitTest assembleRelease
# 产物：app/build/outputs/apk/release/app-release.apk
```

## 签名

- 默认使用仓库内的 `keystore/shared-debug.jks`（密码公开：`android`）。它的作用只是让每次 CI 构建的签名保持一致，
  手机上可以直接覆盖升级；**不具备防伪作用**。
- 如需正式签名，在仓库 Settings → Secrets and variables → Actions 中添加：
  `ANDROID_KEYSTORE_BASE64`（`base64 -w0 release.jks` 的结果）、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD`，
  之后的构建会自动改用正式密钥（切换密钥后需要先卸载旧版本再安装）。
