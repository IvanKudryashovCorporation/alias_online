from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import save_profile, update_profile
from ui import AppButton, AppTextInput, BodyLabel, BrandTitle, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font, resolve_image_source


class SubtleActionButton(ButtonBehavior, Label):
    def __init__(self, text="", **kwargs):
        register_game_font()
        super().__init__(size_hint_y=None, height=dp(22), **kwargs)
        self.text = text
        self.font_name = "GameFont"
        self.font_size = sp(12)
        self.color = COLORS["text_muted"]
        self.halign = "center"
        self.valign = "middle"
        self.opacity = 0.85
        self.bind(size=self._sync_text)

    def _sync_text(self, *_):
        self.text_size = self.size

    def on_press(self):
        self.opacity = 0.55

    def on_release(self):
        self.opacity = 0.85


class AvatarPreview(BoxLayout):
    def __init__(self, **kwargs):
        register_game_font()
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(dp(88), dp(88)),
            **kwargs,
        )

        from kivy.graphics import Color, Line, Rectangle

        with self.canvas.before:
            self._bg_color = Color(*COLORS["avatar_placeholder_bg"])
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.2, rectangle=(self.x, self.y, self.width, self.height))

        self._image = Image(fit_mode="cover", opacity=0)
        self.add_widget(self._image)

        self._placeholder = PixelLabel(
            text="?",
            font_size=sp(22),
            color=COLORS["avatar_placeholder_text"],
            center=True,
        )
        self.add_widget(self._placeholder)

        self.bind(pos=self._sync_children, size=self._sync_children)

    def _sync_children(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rectangle = (self.x, self.y, self.width, self.height)

        self._image.pos = (self.x + dp(2), self.y + dp(2))
        self._image.size = (self.width - dp(4), self.height - dp(4))
        self._placeholder.pos = self.pos
        self._placeholder.size = self.size
        self._placeholder.text_size = self.size

    def set_avatar(self, source=None):
        resolved_source = resolve_image_source(source)
        self._image.source = resolved_source or ""
        if resolved_source:
            self._image.reload()
        self._image.opacity = 1 if resolved_source else 0
        self._placeholder.opacity = 0 if resolved_source else 1
        self._bg_color.rgba = COLORS["surface_strong"] if resolved_source else COLORS["avatar_placeholder_bg"]


class RegistrationScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.selected_avatar_path = None
        self.avatar_picker_popup = None
        self.profile_mode = False
        self.default_content_spacing = dp(8)
        self.compact_content_spacing = dp(4)
        self.default_content_padding = [dp(18), dp(16), dp(18), dp(18)]
        self.compact_content_padding = [dp(12), dp(10), dp(12), dp(10)]
        self.default_card_padding = [dp(16), dp(14), dp(16), dp(14)]
        self.compact_card_padding = [dp(18), dp(12), dp(18), dp(12)]
        self.default_card_spacing = dp(8)
        self.compact_card_spacing = dp(4)
        self.default_input_padding = [dp(16), dp(18), dp(16), dp(12)]
        self.profile_input_padding = [dp(14), dp(12), dp(14), dp(12)]

        root = ScreenBackground()

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=self.default_content_spacing,
            padding=self.default_content_padding,
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        self.content = content

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
        self.back_btn = AppButton(text="\u041d\u0430\u0437\u0430\u0434", compact=True, size_hint=(None, None), size=(dp(128), dp(42)))
        self.back_btn.bind(on_release=self._go_back)
        top_bar.add_widget(self.back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        self.brand_title = BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3))
        content.add_widget(self.brand_title)

        self.top_spacer = Widget(size_hint_y=None, height=dp(10))
        content.add_widget(self.top_spacer)

        self.card = RoundedPanel(
            orientation="vertical",
            padding=self.default_card_padding,
            spacing=self.default_card_spacing,
            size_hint_y=None,
            height=dp(560),
        )

        self.title_label = PixelLabel(text="\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f", font_size=sp(18), center=True, size_hint_y=None)
        self.card.add_widget(self.title_label)

        self.subtitle_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(32))
        self.subtitle_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="\u0421\u043e\u0437\u0434\u0430\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u0432 \u0438\u0433\u0440\u0443.",
        )
        self.subtitle_row.add_widget(self.subtitle_label)
        self.card.add_widget(self.subtitle_row)

        self.name_input = AppTextInput(hint_text="\u0418\u043c\u044f", height=dp(48))
        self.email_input = AppTextInput(hint_text="E-mail", height=dp(48))
        self.password_input = AppTextInput(hint_text="\u041f\u0430\u0440\u043e\u043b\u044c", password=True, height=dp(48))
        self.name_input.padding = self.default_input_padding[:]
        self.email_input.padding = self.default_input_padding[:]
        self.password_input.padding = self.default_input_padding[:]

        self.name_caption_row = BoxLayout(orientation="vertical", size_hint_y=None, height=0, opacity=0)
        self.name_caption = BodyLabel(
            text="\u041d\u0438\u043a\u043d\u0435\u0439\u043c",
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
        )
        self.name_caption_row.add_widget(self.name_caption)

        self.email_caption_row = BoxLayout(orientation="vertical", size_hint_y=None, height=0, opacity=0)
        self.email_caption = BodyLabel(
            text="E-mail",
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
        )
        self.email_caption_row.add_widget(self.email_caption)

        self.password_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(48))
        self.password_row.add_widget(self.password_input)
        self.card.add_widget(self.name_caption_row)
        self.card.add_widget(self.name_input)
        self.card.add_widget(self.email_caption_row)
        self.card.add_widget(self.email_input)
        self.card.add_widget(self.password_row)

        self.avatar_mode_note_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(22))
        self.avatar_mode_note = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            text="\u0410\u0432\u0430\u0442\u0430\u0440 \u043c\u043e\u0436\u043d\u043e \u0431\u0443\u0434\u0435\u0442 \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u043e\u0437\u0436\u0435 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435.",
        )
        self.avatar_mode_note_row.add_widget(self.avatar_mode_note)
        self.card.add_widget(self.avatar_mode_note_row)

        self.avatar_section = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=0, opacity=0)

        self.preview_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(92))
        self.avatar_preview = AvatarPreview()
        self.preview_row.add_widget(Widget())
        self.preview_row.add_widget(self.avatar_preview)
        self.preview_row.add_widget(Widget())
        self.avatar_section.add_widget(self.preview_row)

        self.avatar_button_gap = Widget(size_hint_y=None, height=dp(12))
        self.avatar_section.add_widget(self.avatar_button_gap)

        self.add_photo_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        self.add_photo_row.add_widget(Widget())
        self.pick_avatar_btn = AppButton(
            text="\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0444\u043e\u0442\u043e",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(210), dp(40)),
        )
        self.pick_avatar_btn.bind(on_release=self.open_avatar_picker)
        self.add_photo_row.add_widget(self.pick_avatar_btn)
        self.add_photo_row.add_widget(Widget())
        self.avatar_section.add_widget(self.add_photo_row)

        self.clear_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0)
        self.clear_row.add_widget(Widget())
        self.clear_avatar_btn = SubtleActionButton(text="\u0423\u0431\u0440\u0430\u0442\u044c \u0444\u043e\u0442\u043e")
        self.clear_avatar_btn.bind(on_release=self.clear_avatar)
        self.clear_row.add_widget(self.clear_avatar_btn)
        self.clear_row.add_widget(Widget())
        self.avatar_section.add_widget(self.clear_row)

        self.card.add_widget(self.avatar_section)

        self.avatar_status_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, opacity=0)
        self.avatar_status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            shorten=True,
            shorten_from="center",
            text="",
        )
        self.avatar_status_row.add_widget(self.avatar_status_label)
        self.card.add_widget(self.avatar_status_row)

        self.bio_input = AppTextInput(
            hint_text="\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)",
            multiline=True,
            height=dp(72),
        )
        self.card.add_widget(self.bio_input)

        self.save_btn = AppButton(text="\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c", font_size=sp(18))
        self.save_btn.height = dp(64)
        self.save_btn.bind(on_release=self.submit_profile)
        self.card.add_widget(self.save_btn)

        self.status_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(36))
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            text="\u041f\u043e\u0441\u043b\u0435 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438 \u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u0433\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e.",
        )
        self.status_row.add_widget(self.status_label)
        self.card.add_widget(self.status_row)

        self.logout_btn = AppButton(
            text="\u0412\u044b\u0445\u043e\u0434 \u0438\u0437 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430",
            compact=False,
            font_size=sp(17),
            button_color=COLORS["danger_button"],
            pressed_color=COLORS["danger_button_pressed"],
        )
        self.logout_btn.size_hint_y = None
        self.logout_btn.height = 0
        self.logout_btn.opacity = 0
        self.logout_btn.disabled = True
        self.logout_btn.bind(on_release=self._logout)
        self.card.add_widget(self.logout_btn)

        content.add_widget(self.card)
        self.bottom_spacer = Widget(size_hint_y=None, height=dp(10))
        content.add_widget(self.bottom_spacer)

        self.scroll.add_widget(content)
        root.add_widget(self.scroll)
        self.add_widget(root)
        self._sync_avatar_actions()

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.back_btn.text = "\u0412 \u043c\u0435\u043d\u044e" if app is not None and app.has_session_access() else "\u041d\u0430\u0437\u0430\u0434"
        self.scroll.scroll_y = 1

        latest_profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
        self._set_profile_mode(latest_profile is not None)

        if latest_profile is None:
            self.name_input.text = ""
            self.email_input.text = ""
            self.password_input.text = ""
            self.bio_input.text = ""
            self.selected_avatar_path = None
            self.avatar_preview.set_avatar(None)
            self.avatar_status_label.color = COLORS["text_muted"]
            self.avatar_status_label.text = ""
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "\u0421\u043e\u0437\u0434\u0430\u0439 \u0430\u043a\u043a\u0430\u0443\u043d\u0442, \u0430 \u0444\u043e\u0442\u043e \u0434\u043e\u0431\u0430\u0432\u0438\u0448\u044c \u043f\u043e\u0437\u0436\u0435 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435."
            return

        self.name_input.text = latest_profile.name
        self.email_input.text = latest_profile.email
        self.password_input.text = ""
        self.bio_input.text = latest_profile.bio or ""
        self.selected_avatar_path = latest_profile.avatar_path
        self.avatar_preview.set_avatar(latest_profile.avatar_source)
        self._apply_profile_summary(latest_profile)
        self.avatar_status_label.color = COLORS["text_muted"]
        self.avatar_status_label.text = Path(latest_profile.avatar_path).name if latest_profile.avatar_path else "\u0424\u043e\u0442\u043e \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u043e."
        self.status_label.color = COLORS["text_muted"]
        self.status_label.text = "\u041c\u043e\u0436\u043d\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0444\u043e\u0442\u043e \u0438 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u043f\u0440\u043e\u0444\u0438\u043b\u044f."
        self._sync_avatar_actions()

    def submit_profile(self, *_):
        try:
            if self.profile_mode:
                app = App.get_running_app()
                current_profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
                if current_profile is None:
                    raise ValueError("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0439\u0434\u0438 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442.")

                profile = update_profile(
                    email=current_profile.email,
                    avatar_path=self.selected_avatar_path,
                    bio=self.bio_input.text,
                )
            else:
                profile = save_profile(
                    name=self.name_input.text,
                    email=self.email_input.text,
                    password=self.password_input.text,
                    avatar_path=None,
                    bio=self.bio_input.text,
                )
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return

        app = App.get_running_app()
        if app is not None:
            app.sign_in(profile)

        self.password_input.text = ""
        self.status_label.color = COLORS["success"]
        if self.profile_mode:
            self.status_label.text = (
                f"\u041f\u0440\u043e\u0444\u0438\u043b\u044c {profile.name} \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d. "
                "\u041f\u0435\u0440\u0435\u0445\u043e\u0434\u0438\u043c \u0432 \u043c\u0435\u043d\u044e."
            )
        else:
            self.status_label.text = (
                f"\u041f\u0440\u043e\u0444\u0438\u043b\u044c {profile.name} \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d. "
                "\u041f\u0435\u0440\u0435\u0445\u043e\u0434\u0438\u043c \u0432 \u043c\u0435\u043d\u044e."
            )
        self.manager.current = "start"

    def open_avatar_picker(self, *_):
        if not self.profile_mode:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "\u0412\u044b\u0431\u043e\u0440 \u0444\u043e\u0442\u043e \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435 \u043f\u043e\u0441\u043b\u0435 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438."
            return

        chooser = FileChooserListView(
            path=str(Path.home()),
            filters=["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"],
            multiselect=False,
        )

        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=[dp(14), dp(14), dp(14), dp(14)])
        body.add_widget(chooser)

        controls = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(52))
        choose_btn = AppButton(text="\u0412\u044b\u0431\u0440\u0430\u0442\u044c", compact=True)
        close_btn = AppButton(text="\u041e\u0442\u043c\u0435\u043d\u0430", compact=True)
        choose_btn.bind(on_release=lambda *_: self.select_avatar_from_picker(chooser))
        close_btn.bind(on_release=lambda *_: self.dismiss_avatar_picker())
        controls.add_widget(choose_btn)
        controls.add_widget(close_btn)
        body.add_widget(controls)

        self.avatar_picker_popup = Popup(
            title="\u0412\u044b\u0431\u043e\u0440 \u0430\u0432\u0430\u0442\u0430\u0440\u0430",
            title_font="GameFont",
            title_size=sp(18),
            content=body,
            size_hint=(0.92, 0.82),
            auto_dismiss=True,
        )
        self.avatar_picker_popup.open()

    def dismiss_avatar_picker(self):
        if self.avatar_picker_popup is not None:
            self.avatar_picker_popup.dismiss()
            self.avatar_picker_popup = None

    def select_avatar_from_picker(self, chooser):
        selection = chooser.selection
        if not selection:
            self.avatar_status_label.color = COLORS["warning"]
            self.avatar_status_label.text = "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u044b\u0431\u0435\u0440\u0438 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0435 \u0432 \u0441\u043f\u0438\u0441\u043a\u0435 \u0444\u0430\u0439\u043b\u043e\u0432."
            return

        chosen_path = str(Path(selection[0]).expanduser().resolve())
        self.selected_avatar_path = chosen_path
        self.avatar_preview.set_avatar(chosen_path)
        self.avatar_status_label.color = COLORS["success"]
        self.avatar_status_label.text = Path(chosen_path).name
        self._sync_avatar_actions()
        self.dismiss_avatar_picker()

    def clear_avatar(self, *_):
        self.selected_avatar_path = None
        self.avatar_preview.set_avatar(None)
        self.avatar_status_label.color = COLORS["text_muted"]
        self.avatar_status_label.text = "\u0424\u043e\u0442\u043e \u0443\u0431\u0440\u0430\u043d\u043e."
        self._sync_avatar_actions()

    def _set_profile_mode(self, enabled):
        self.profile_mode = enabled

        if enabled:
            self.title_label.text = "\u041f\u0440\u043e\u0444\u0438\u043b\u044c"
            self.title_label.font_size = sp(18)
            self.subtitle_label.text = ""
            self.subtitle_label.font_size = sp(10.5)
            self.avatar_mode_note.text = "\u0424\u043e\u0442\u043e \u043f\u0440\u043e\u0444\u0438\u043b\u044f"
            self.scroll.do_scroll_y = False
            self.content.spacing = self.compact_content_spacing
            self.content.padding = self.compact_content_padding
            self.card.spacing = self.compact_card_spacing
            self.card.padding = self.compact_card_padding
            self.brand_title.height = dp(68)
            self.top_spacer.height = dp(8)
            self.bottom_spacer.height = dp(2)
            self.subtitle_row.height = dp(18)
            self.subtitle_row.opacity = 1
            self.name_caption_row.height = dp(16)
            self.name_caption_row.opacity = 1
            self.email_caption.text = "E-mail"
            self.email_caption_row.height = dp(16)
            self.email_caption_row.opacity = 1
            self.name_input.height = dp(44)
            self.email_input.height = dp(44)
            self.name_input.padding = self.profile_input_padding[:]
            self.email_input.padding = self.profile_input_padding[:]
            self.name_input.readonly = True
            self.email_input.readonly = True
            self.name_input.disabled = False
            self.email_input.disabled = False
            self.password_row.height = 0
            self.password_row.opacity = 0
            self.password_input.disabled = True
            self.avatar_mode_note_row.height = 0
            self.avatar_mode_note_row.opacity = 0
            self.avatar_preview.size = (dp(76), dp(76))
            self.preview_row.height = dp(78)
            self.avatar_button_gap.height = dp(6)
            self.add_photo_row.height = dp(36)
            self.pick_avatar_btn.size = (dp(188), dp(36))
            self.avatar_section.height = dp(146)
            self.avatar_section.opacity = 1
            self.avatar_status_row.height = dp(18)
            self.avatar_status_row.opacity = 1
            self.bio_input.height = dp(52)
            self.bio_input.hint_text = "\u0420\u0430\u0441\u0441\u043a\u0430\u0436\u0438 \u043f\u0430\u0440\u0443 \u0441\u043b\u043e\u0432 \u043e \u0441\u0435\u0431\u0435"
            self.pick_avatar_btn.disabled = False
            self.save_btn.height = dp(46)
            self.status_row.height = 0
            self.status_row.opacity = 0
            self.card.height = dp(470)
            self.logout_btn.disabled = False
            self.logout_btn.opacity = 1
            self.logout_btn.height = dp(46)
            self._sync_avatar_actions()
            self.save_btn.text = "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f"
            return

        self.title_label.text = "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f"
        self.title_label.font_size = sp(18)
        self.subtitle_label.text = "\u0421\u043e\u0437\u0434\u0430\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u0432 \u0438\u0433\u0440\u0443."
        self.subtitle_label.font_size = sp(12)
        self.avatar_mode_note.text = "\u0410\u0432\u0430\u0442\u0430\u0440 \u043c\u043e\u0436\u043d\u043e \u0431\u0443\u0434\u0435\u0442 \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u043e\u0437\u0436\u0435 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435."
        self.scroll.do_scroll_y = False
        self.content.spacing = self.default_content_spacing
        self.content.padding = self.default_content_padding
        self.card.spacing = self.default_card_spacing
        self.card.padding = self.default_card_padding
        self.brand_title.height = dp(136)
        self.top_spacer.height = dp(10)
        self.bottom_spacer.height = dp(10)
        self.subtitle_row.height = dp(32)
        self.subtitle_row.opacity = 1
        self.name_caption_row.height = 0
        self.name_caption_row.opacity = 0
        self.email_caption_row.height = 0
        self.email_caption_row.opacity = 0
        self.name_input.height = dp(48)
        self.email_input.height = dp(48)
        self.name_input.padding = self.default_input_padding[:]
        self.email_input.padding = self.default_input_padding[:]
        self.password_input.padding = self.default_input_padding[:]
        self.name_input.readonly = False
        self.email_input.readonly = False
        self.name_input.disabled = False
        self.email_input.disabled = False
        self.password_row.height = dp(48)
        self.password_row.opacity = 1
        self.password_input.disabled = False
        self.avatar_mode_note_row.height = dp(22)
        self.avatar_mode_note_row.opacity = 1
        self.avatar_preview.size = (dp(88), dp(88))
        self.preview_row.height = dp(92)
        self.avatar_button_gap.height = dp(12)
        self.add_photo_row.height = dp(42)
        self.pick_avatar_btn.size = (dp(210), dp(40))
        self.avatar_section.height = 0
        self.avatar_section.opacity = 0
        self.avatar_status_row.height = 0
        self.avatar_status_row.opacity = 0
        self.bio_input.height = dp(72)
        self.bio_input.hint_text = "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)"
        self.pick_avatar_btn.disabled = True
        self.clear_avatar_btn.disabled = True
        self.clear_avatar_btn.opacity = 0
        self.clear_avatar_btn.height = 0
        self.clear_row.height = 0
        self.save_btn.height = dp(64)
        self.status_row.height = dp(36)
        self.status_row.opacity = 1
        self.card.height = dp(560)
        self.logout_btn.disabled = True
        self.logout_btn.opacity = 0
        self.logout_btn.height = 0
        self.save_btn.text = "\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c"

    def _apply_profile_summary(self, profile):
        joined_label = self._format_profile_date(profile.created_at)
        self.subtitle_label.text = f"\u041a\u043e\u0434 \u0438\u0433\u0440\u043e\u043a\u0430 #{profile.id}  •  \u0432 \u0438\u0433\u0440\u0435 \u0441 {joined_label}"

    def _format_profile_date(self, created_at):
        raw_value = (created_at or "").strip()
        if not raw_value:
            return "--.--.----"

        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return raw_value

        return parsed.strftime("%d.%m.%Y")

    def _sync_avatar_actions(self):
        if not self.profile_mode:
            self.clear_avatar_btn.disabled = True
            self.clear_avatar_btn.opacity = 0
            self.clear_avatar_btn.height = 0
            self.clear_row.height = 0
            return

        has_avatar = bool(self.selected_avatar_path)
        self.clear_avatar_btn.disabled = not has_avatar
        self.clear_avatar_btn.opacity = 0.85 if has_avatar else 0
        self.clear_avatar_btn.height = dp(22) if has_avatar else 0
        self.clear_row.height = dp(14) if has_avatar else 0

    def _go_back(self, *_):
        app = App.get_running_app()
        if app is not None and app.has_session_access():
            self.manager.current = "start"
            return
        self.manager.current = "entry"

    def _logout(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.sign_out()
        self.manager.current = "entry"
