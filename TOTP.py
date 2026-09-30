import wx
import pyotp
import time
import threading
import configparser
import os
import urllib.request
import urllib.error

# 高分DPI感知开启
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except OSError:
    pass


class TotpCard(wx.Panel):
    """独立验证码卡片绘制类"""
    def __init__(self, parent):
        super().__init__(parent, size=(-1, 170), style=wx.BORDER_NONE)
        self.code_text = "------"
        self.remain_second = 30
        self.Bind(wx.EVT_PAINT, self.OnPaintEvent)

    def SetDisplayContent(self, code: str, remain: int):
        self.code_text = code
        self.remain_second = remain
        self.Refresh()

    def OnPaintEvent(self, event):
        dc = wx.PaintDC(self)
        w, h = self.GetClientSize()
        # 圆角卡片背景
        back_color = wx.Colour(20, 24, 34)
        border_color = wx.Colour(60, 68, 82)
        dc.SetBrush(wx.Brush(back_color))
        dc.SetPen(wx.Pen(border_color, width=2))
        dc.DrawRoundedRectangle(10, 10, w - 20, h - 20, 14)

        # ========== 验证码【楷体，加粗】==========
        code_font = wx.Font(46, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName="楷体")
        dc.SetFont(code_font)
        dc.SetTextForeground(wx.Colour(245, 247, 250))
        show_code = f"{self.code_text[:3]} {self.code_text[3:]}"
        text_w, text_h = dc.GetTextExtent(show_code)
        dc.DrawText(show_code, (w - text_w) // 2, 32)

        # ========== 剩余秒文字：微软雅黑 ==========
        tip_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Microsoft YaHei")
        dc.SetFont(tip_font)
        dc.SetTextForeground(wx.Colour(170, 180, 195))
        time_str = f"剩余 {self.remain_second} 秒"
        tw, th = dc.GetTextExtent(time_str)
        dc.DrawText(time_str, (w - tw) // 2, 105)


class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(None, title="TOTP 客户端", size=(560, 560))
        self.SetMinSize((520, 480))
        # ============新增开始============
        # 禁止最大化、禁止全屏
        self.SetMaxSize(self.GetSize())
        self.SetWindowStyle(self.GetWindowStyle() & ~wx.MAXIMIZE_BOX)
        # ============新增结束============
        self.totp_instance = None
        self.run_flag = True

        # ===== 自动获取py脚本所在目录，ini放在同目录 =====
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.ini_file_path = os.path.join(self.script_dir, "accounts.ini")

        # 账号数据结构：用户名 -> {"secret": xxx, "url": xxx}
        self.account_dict = {}

        self.main_panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ========== 账号管理区域 ==========
        acc_sizer = wx.StaticBoxSizer(wx.StaticBox(self.main_panel, label="账号管理"), wx.VERTICAL)

        # 用户名（节名）
        row_name = wx.BoxSizer(wx.HORIZONTAL)
        row_name.Add(wx.StaticText(self.main_panel, label="用户名："), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_username = wx.ComboBox(self.main_panel, choices=[], style=wx.CB_DROPDOWN)
        row_name.Add(self.cb_username, proportion=1, flag=wx.EXPAND | wx.LEFT, border=8)
        acc_sizer.Add(row_name, flag=wx.EXPAND | wx.ALL, border=8)

        # 网址
        row_url = wx.BoxSizer(wx.HORIZONTAL)
        row_url.Add(wx.StaticText(self.main_panel, label="网址："), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_url = wx.TextCtrl(self.main_panel)
        row_url.Add(self.text_url, proportion=1, flag=wx.EXPAND | wx.LEFT, border=8)
        acc_sizer.Add(row_url, flag=wx.EXPAND | wx.ALL, border=8)

        # Base32密钥
        row_secret = wx.BoxSizer(wx.HORIZONTAL)
        row_secret.Add(wx.StaticText(self.main_panel, label="Base32密钥："), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_secret = wx.TextCtrl(self.main_panel)
        row_secret.Add(self.text_secret, proportion=1, flag=wx.EXPAND | wx.LEFT, border=8)
        acc_sizer.Add(row_secret, flag=wx.EXPAND | wx.ALL, border=8)

        # 按钮：保存账号 / 删除账号 / 检测协议 / 打开网站
        btn_sizer_1 = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_save = wx.Button(self.main_panel, label="保存账号")
        self.btn_delete = wx.Button(self.main_panel, label="删除账号")
        self.btn_detect_protocol = wx.Button(self.main_panel, label="检测协议")
        self.btn_open_site = wx.Button(self.main_panel, label="打开网站")

        self.btn_save.Bind(wx.EVT_BUTTON, self.OnSaveAccount)
        self.btn_delete.Bind(wx.EVT_BUTTON, self.OnDeleteAccount)
        self.btn_detect_protocol.Bind(wx.EVT_BUTTON, self.OnDetectProtocol)
        self.btn_open_site.Bind(wx.EVT_BUTTON, self.OnOpenSite)

        btn_sizer_1.Add(self.btn_save, proportion=1, flag=wx.EXPAND)
        btn_sizer_1.Add(self.btn_delete, proportion=1, flag=wx.EXPAND)
        btn_sizer_1.Add(self.btn_detect_protocol, proportion=1, flag=wx.EXPAND)
        btn_sizer_1.Add(self.btn_open_site, proportion=1, flag=wx.EXPAND)
        acc_sizer.Add(btn_sizer_1, flag=wx.EXPAND | wx.ALL, border=8)

        self.main_sizer.Add(acc_sizer, flag=wx.EXPAND | wx.ALL, border=10)

        # ========== 验证码卡片 ==========
        self.code_card = TotpCard(self.main_panel)
        self.main_sizer.Add(self.code_card, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # ========== 倒计时进度条 ==========
        self.timer_gauge = wx.Gauge(self.main_panel, range=30, size=(-1, 24))
        self.main_sizer.Add(self.timer_gauge, flag=wx.EXPAND | wx.ALL, border=10)

        # ========== 复制按钮 ==========
        self.btn_copy_code = wx.Button(self.main_panel, label="复制验证码")
        self.btn_copy_code.Bind(wx.EVT_BUTTON, self.OnCopyCode)
        self.main_sizer.Add(self.btn_copy_code, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.main_panel.SetSizer(self.main_sizer)

        # 事件绑定
        self.cb_username.Bind(wx.EVT_COMBOBOX, self.OnAccountSelect)
        self.text_url.Bind(wx.EVT_TEXT, self.OnUrlTextChanged)
        self.Bind(wx.EVT_CLOSE, self.OnWindowClose)

        # 加载本地INI账号
        self.LoadAccountsFromIni()

        # 启动后台刷新线程
        self.refresh_thread = threading.Thread(target=self.TotpRefreshLoop, daemon=True)
        self.refresh_thread.start()

    # ==================== 账号读取与兼容 ====================
    def LoadAccountsFromIni(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.ini_file_path):
            config.read(self.ini_file_path, encoding="utf-8")
            for section in config.sections():
                secret = config[section].get("secret", "").strip()
                url = config[section].get("url", "").strip()
                self.account_dict[section] = {"secret": secret, "url": url}
        self.cb_username.SetItems(list(self.account_dict.keys()))

    # ==================== 保存账号（自动升级新格式） ====================
    def SaveAccountToIni(self, username: str, secret: str, url: str):
        config = configparser.ConfigParser()
        if os.path.exists(self.ini_file_path):
            config.read(self.ini_file_path, encoding="utf-8")

        config[username] = {
            "url": url.strip(),
            "secret": secret.strip()
        }

        with open(self.ini_file_path, "w", encoding="utf-8") as fp:
            config.write(fp)

        self.account_dict[username] = {"secret": secret.strip(), "url": url.strip()}
        self.cb_username.SetItems(list(self.account_dict.keys()))

    # ==================== 删除账号 ====================
    def RemoveAccountFromIni(self, username: str):
        config = configparser.ConfigParser()
        if os.path.exists(self.ini_file_path):
            config.read(self.ini_file_path, encoding="utf-8")
            if username in config.sections():
                config.remove_section(username)
                with open(self.ini_file_path, "w", encoding="utf-8") as fp:
                    config.write(fp)

        if username in self.account_dict:
            del self.account_dict[username]

        self.cb_username.SetItems(list(self.account_dict.keys()))

    # ==================== 保存按钮 ====================
    def OnSaveAccount(self, event):
        username = self.cb_username.GetValue().strip()
        secret = self.text_secret.GetValue().strip()
        url = self.text_url.GetValue().strip()

        if not username:
            wx.MessageBox("用户名不能为空", "提示", wx.ICON_INFORMATION)
            return

        if not secret:
            wx.MessageBox("Base32密钥不能为空", "提示", wx.ICON_INFORMATION)
            return

        try:
            pyotp.TOTP(secret)
        except Exception as err:
            wx.MessageBox(f"Base32密钥无效：{err}", "错误", wx.ICON_ERROR)
            return

        self.SaveAccountToIni(username, secret, url)
        wx.MessageBox("账号保存成功", "完成")

    # ==================== 删除按钮 ====================
    def OnDeleteAccount(self, event):
        username = self.cb_username.GetValue().strip()
        if username not in self.account_dict:
            wx.MessageBox("选中的账号不存在", "提示", wx.ICON_INFORMATION)
            return

        self.RemoveAccountFromIni(username)
        self.text_secret.SetValue("")
        self.text_url.SetValue("")
        self.totp_instance = None
        self.code_card.SetDisplayContent("------", 30)
        self.timer_gauge.SetValue(0)
        wx.MessageBox("账号已删除", "完成")

    # ==================== 账号选择 ====================
    def OnAccountSelect(self, event):
        username = self.cb_username.GetValue().strip()
        info = self.account_dict.get(username)

        if info:
            self.text_secret.SetValue(info.get("secret", ""))
            self.text_url.SetValue(info.get("url", ""))

            try:
                self.totp_instance = pyotp.TOTP(info["secret"])
            except Exception:
                self.totp_instance = None
        else:
            self.text_secret.SetValue("")
            self.text_url.SetValue("")
            self.totp_instance = None

        self.UpdateOpenSiteButtonState()

    # ==================== 网址输入变化时，更新打开按钮状态 ====================
    def OnUrlTextChanged(self, event):
        self.UpdateOpenSiteButtonState()

    def UpdateOpenSiteButtonState(self):
        url = self.text_url.GetValue().strip().lower()
        if url.startswith("http://") or url.startswith("https://"):
            self.btn_open_site.Enable()
        else:
            self.btn_open_site.Disable()

    # ==================== 打开网站 ====================
    def OnOpenSite(self, event):
        url = self.text_url.GetValue().strip()
        if not url:
            wx.MessageBox("网址为空，无法打开", "提示", wx.ICON_INFORMATION)
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            wx.MessageBox("仅支持 http:// 和 https:// 协议", "提示", wx.ICON_INFORMATION)
            return

        try:
            wx.LaunchDefaultBrowser(url)
        except Exception as err:
            wx.MessageBox(f"打开网站失败：{err}", "错误", wx.ICON_ERROR)

    # ==================== 检测协议（只测 http / https） ====================
    def OnDetectProtocol(self, event):
        raw = self.text_url.GetValue().strip()
        if not raw:
            wx.MessageBox("请先输入网址或域名", "提示", wx.ICON_INFORMATION)
            return

        # 已经带协议，不重复探测
        if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
            wx.MessageBox("已有协议，无需检测", "提示", wx.ICON_INFORMATION)
            return

        # 启动后台线程探测
        self.btn_detect_protocol.Disable()
        self.btn_detect_protocol.SetLabel("检测中...")
        threading.Thread(target=self.DetectProtocolWorker, args=(raw,), daemon=True).start()

    def DetectProtocolWorker(self, raw_domain: str):
        result_url = None
        error_msg = ""

        # 优先 HTTPS
        for protocol in ("https://", "http://"):
            test_url = protocol + raw_domain
            try:
                req = urllib.request.Request(test_url, method="HEAD")
                urllib.request.urlopen(req, timeout=3)
                result_url = test_url
                break
            except urllib.error.HTTPError as err:
                # 服务器有响应，说明协议可用
                result_url = test_url
                break
            except (urllib.error.URLError, TimeoutError, Exception) as err:
                error_msg = str(err)
                continue

        if result_url:
            wx.CallAfter(self.OnDetectSuccess, result_url)
        else:
            wx.CallAfter(self.OnDetectFailed, raw_domain, error_msg)

    def OnDetectSuccess(self, url: str):
        self.text_url.SetValue(url)
        self.btn_detect_protocol.SetLabel("检测协议")
        self.btn_detect_protocol.Enable()
        wx.MessageBox(f"检测成功：{url}", "完成")

    def OnDetectFailed(self, raw_domain: str, error_msg: str):
        self.btn_detect_protocol.SetLabel("检测协议")
        self.btn_detect_protocol.Enable()
        wx.MessageBox(
            f"无法访问 {raw_domain}，已保留原始输入。\n错误信息：{error_msg}",
            "检测失败",
            wx.ICON_WARNING
        )

    # ==================== TOTP 刷新循环 ====================
    def TotpRefreshLoop(self):
        while self.run_flag:
            if self.totp_instance is not None:
                remain_sec = 30 - (time.time() % 30)
                current_code = self.totp_instance.now()
                remain_int = int(remain_sec)
                wx.CallAfter(self.UpdateAllUi, current_code, remain_int)
            time.sleep(0.2)

    def UpdateAllUi(self, code, remain):
        self.code_card.SetDisplayContent(code, remain)
        self.timer_gauge.SetValue(remain)

    # ==================== 复制验证码 ====================
    def OnCopyCode(self, event):
        if self.totp_instance is None:
            wx.MessageBox("请先选择或加载有效账号密钥", "提示")
            return
        code = self.totp_instance.now()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(code))
            wx.TheClipboard.Close()
            wx.MessageBox(f"验证码 {code} 已复制到剪贴板", "复制成功")

    # ==================== 窗口关闭 ====================
    def OnWindowClose(self, event):
        self.run_flag = False
        event.Skip()


if __name__ == "__main__":
    app = wx.App(False)
    win = MainWindow()
    win.Show()
    app.MainLoop()
