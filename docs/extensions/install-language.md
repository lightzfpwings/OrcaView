# Install the OrcaView language extension · 安装语言扩展

Extract the entire ZIP into a folder you intend to keep. Its `languages` folder contains the interface translations and their matching Qt dialog translations.

| Interface | Locale |
| --- | --- |
| 简体中文 | `zh-Hans` |
| 繁體中文 | `zh-Hant` |
| Deutsch | `de` |
| 日本語 | `ja` |

## Desktop

1. Open **View → Interface language… → Choose folder…** and select the extracted **languages** folder.
2. Select the language, click **Save**, then restart OrcaView. To switch back, select **English** and restart.
3. Keep the folder in place. If you move it, select its new location in the same dialog.

**简体中文**　完整解压 ZIP。打开 **View → Interface language… → Choose folder…**，选择解压得到的 **languages** 文件夹。选中“简体中文”，保存并重启。请保留这个文件夹。

**繁體中文**　完整解壓縮 ZIP。在 **View → Interface language… → Choose folder…** 選取解壓後的 **languages** 資料夾，選擇「繁體中文」、儲存並重新啟動。請保留這個資料夾。

**Deutsch**　Das ZIP-Archiv vollständig entpacken. Unter **View → Interface language… → Choose folder…** den entpackten Ordner **languages** und anschließend **Deutsch** auswählen. Mit **Save** speichern und OrcaView neu starten. Den Ordner danach beibehalten.

**日本語**　ZIP をすべて展開します。**View → Interface language… → Choose folder…** から展開した **languages** フォルダーを選び、**日本語** を選択します。**Save** で保存し、OrcaView を再起動してください。展開したフォルダーはそのまま残してください。

## Command line · 命令行

Run these commands from the folder containing this guide.

```sh
orcaview settings language --directory ./languages --locale zh-Hans
orcaview settings language
```

Replace `zh-Hans` with the desired locale. Use `en` for built-in English. With a packaged app, replace `orcaview` with the path to its executable, for example `/Applications/OrcaView.app/Contents/MacOS/OrcaView` on macOS, `/path/to/OrcaView` on Linux or `& 'C:\Apps\OrcaView\OrcaView.exe'` in PowerShell. Launch a new OrcaView window to use the saved language.

扩展作者可在 `authoring/` 找到英文消息模板与 JSON 格式定义。For a new language, copy the template from `authoring/` into `languages/`, set a unique locale and display name, and translate message values while preserving placeholders.
