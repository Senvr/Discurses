"""
Everything UI
"""
import datetime
import re
import sys
from typing import List

import discord
import urwid
from discord import Channel, Message

import processing
from main import DiscordClient


class MainUI:
    palette = [
        ("focus", "dark red", "", "standout"),
        ("dim", "dark cyan", "", "standout"),
        ("head", "light red", ""),
        ("message_timestamp", "dark cyan", "", ""),
        ("message_channel", "dark green", "", ""),
        ("message_author", "light blue", "", ""),
        ("message_content", "white", "", ""),
        ("message_channel_cur", "light green", "", "bold"),
        ("message_timestamp_f", "black", "dark cyan", "bold"),
        ("message_channel_f", "black", "dark green", "bold"),
        ("message_author_f", "black", "light blue", "bold"),
        ("message_content_f", "black", "white", "bold"),
        ("message_channel_cur_f", "black", "light green", "bold"),
        ("send_channel_selector", "light red", "", ""),
        ("send_channel_selector_f", "black", "light red", ""),
        ("send_channel_selector_sel", "", "dark red", ""),
        ("send_channel_selector_sel_f", "black", "light red", ""),
        ("servtree_channel", "", "", ""),
        ("servtree_channel_f", "black", "white", "bold"),
        ("servtree_server", "", "", ""),
        ("servtree_server_f", "black", "white", "bold"),
        ("sidebar_user_on", "dark green", "", ""),
        ("sidebar_user_off", "dark red", "", ""),
        ("sidebar_user_idle", "yellow", "", ""),
        ("sidebar_user_on_f", "black", "dark green", ""),
        ("sidebar_user_off_f", "black", "dark red", ""),
        ("sidebar_user_idle_f", "black", "yellow", ""),
    ]

    def __init__(self, discord_client: DiscordClient):
        self.discord = discord_client
        self.tabs = []
        header = urwid.AttrMap(urwid.Text("Logging in"), "head")
        self.frame = urwid.Frame(
            urwid.Filler(
                urwid.Text(
                    """
 ___________________________ 
< Logging in... Hang tight! >
 --------------------------- 
        \   ^__^             
         \  (oo)\_______     
            (__)\       )\/\ 
                ||----w |    
                ||     ||    

        """,
                    align=urwid.CENTER)),
            header=header)
        self.urwid_loop = urwid.MainLoop(
            self.frame,
            palette=MainUI.palette,
            unhandled_input=self._keypress,
            event_loop=urwid.AsyncioEventLoop(loop=self.discord.loop),
            pop_ups=True)

        def refresh(_loop, _data):
            _loop.draw_screen()
            _loop.set_alarm_in(2, refresh)

        self.urwid_loop.set_alarm_in(0.2, refresh)

        self.urwid_loop.start()

    def _keypress(self, input):
        if input is None:
            return
        if input in ("Q"):
            self.urwid_loop.stop()
            raise urwid.ExitMainLoop()
        match = re.fullmatch("meta ([0-9])", input)
        if match is not None:
            index = int(match.group(1))
            self.notify("Tab: {0}".format(index))
            if index == 0:
                index = 10
            self.set_body(self.tabs[index - 1])
        

    def set_body(self, w):
        self.frame.set_body(w)
        self.draw_screen()

    def notify(self, string):
        string = str(string)
        self.frame.set_header(urwid.AttrWrap(urwid.Text(string), "head"))

    def draw_screen(self):
        self.urwid_loop.draw_screen()

    def on_ready(self):
        for i in range(0, 9):
            self.tabs.append(ChatWidget(self.discord, [], None))
        self.set_body(self.tabs[0])


########################
# Chat related widgets #
########################


class ChatWidget(urwid.WidgetWrap):
    """This widget holds:
        1. A MessageListWidget of all the messages in channels
        2. A EditMessageWidget, sending messages to send_channel
    """

    def __init__(self, discord_client: DiscordClient, channels: List[Channel],
                 send_channel: Channel):
        self.discord = discord_client
        self.ui = self.discord.ui
        self.channels = channels
        self.send_channel = send_channel
        self._selectable = False
        self.channel_names = processing.shorten_channel_names(channels, 14)
        self.w_channel_cols = SendChannelSelector(self)
        self.message_list = MessageListWidget(self.discord, self)
        self.edit_message = MessageEditWidget(self.discord, self)
        self.frame = urwid.Pile([('weight', 1, self.message_list),
                                 ('pack', self.edit_message),
                                 ('pack', self.w_channel_cols)], 1)
        self.pop_up = urwid.Frame(urwid.WidgetPlaceholder(None))
        self.pop_up_overlay = urwid.Overlay(
            urwid.LineBox(self.pop_up), self.frame, 'center', ('relative', 60),
            'middle', ('relative', 60))
        self.w_placeholder = urwid.WidgetPlaceholder(self.frame)
        self.__super.__init__(self.w_placeholder)
        if len(channels) == 0:
            self.open_pop_up(ServerTree(self))

    def keypress(self, size, key):
        key = self._w.keypress(size, key)
        if key == None:
            return
        if key in ("s", "ctrl s"):
            self.open_pop_up(ServerTree(self))
            return
        if key == "up":
            if self.frame.focus_position > 0:
                self.frame.focus_position -= 1
                return
        if key == "down":
            if self.frame.focus_position < len(self.frame.widget_list) - 1:
                self.frame.focus_position += 1
                return
        if re.match("meta [0-9]", key):
            return self.ui._keypress(key)
        return key

    def channel_list_updated(self):
        self.channel_names = processing.shorten_channel_names(self.channels,
                                                              14)
        self.message_list.list_walker.invalidate()
        self.message_list.w_sidebar.update_list()
        self.w_channel_cols.update_columns()

    def open_pop_up(self, widget, header=None, footer=None):
        self.pop_up.body.original_widget = widget
        self.pop_up.header = header
        self.pop_up.footer = footer
        self.w_placeholder.original_widget = self.pop_up_overlay

    def close_pop_up(self):
        self.pop_up.body.original_widget = None
        self.pop_up.header = None
        self.pop_up.footer = None
        self.w_placeholder.original_widget = self.frame


class ServerTree(urwid.WidgetWrap):
    def __init__(self, chat_widget: ChatWidget):
        self.chat_widget = chat_widget
        items = []
        for server in chat_widget.discord.servers:
            node = {"name": server.name, "children": []}
            for ch in server.channels:
                node['children'].append({
                    'name': ch.name,
                    'server_tree': self,
                    'channel': ch
                })

            nodeobj = ServerTree.TreeNodeServer(node)
            nodeobj.expanded = False
            items.append(nodeobj)

        self.w_listbox = urwid.TreeListBox(ServerTree.TreeWalker(items))
        self.__super.__init__(self.w_listbox)

    def selectable(self):
        return True

    def keypress(self, size, key):
        return self.w_listbox.keypress(size, key)

    class TreeWidgetChannel(urwid.TreeWidget):
        def get_display_text(self):
            return self.get_node().get_value()['name']

        def load_inner_widget(self):
            return urwid.AttrMap(urwid.Text(self.get_display_text()), "servtree_channel", "servtree_channel_f")

        def keypress(self, size, key):
            server_tree = self.get_node().get_value()['server_tree']
            channel = self.get_node().get_value()['channel']
            if key == "enter":
                server_tree.chat_widget.channels.append(channel)
                server_tree.chat_widget.channel_list_updated()
                server_tree.chat_widget.close_pop_up()
                return
            if key in (" ", "s"):
                server_tree.chat_widget.channels.append(channel)
                server_tree.chat_widget.channel_list_updated()
                return
            if key in ("esc", "q"):
                server_tree.chat_widget.close_pop_up()
                return
            return key

        def selectable(self):
            return True

    class TreeWidgetServer(urwid.TreeWidget):

        def __init__(self, node):
            self._node = node
            self._innerwidget = None
            self.is_leaf = False
            self.expanded = False
            widget = self.get_indented_widget()
            urwid.WidgetWrap.__init__(self, widget)

        def get_display_text(self):
            return self.get_node().get_value()['name'] + ": " + str(len(self.get_node().get_value()['children']))

        def load_inner_widget(self):
            return urwid.AttrMap(urwid.Text(self.get_display_text()), "servtree_server", "servtree_server_f")

        def keypress(self, size, key):
            if key == "left":
                key = "-"
            return urwid.TreeWidget.keypress(self, size, key)

    class TreeNodeChannel(urwid.TreeNode):
        def load_widget(self):
            return ServerTree.TreeWidgetChannel(self)

    class TreeNodeServer(urwid.ParentNode):

        def load_widget(self):
            return ServerTree.TreeWidgetServer(self)

        def load_child_keys(self):
            data = self.get_value()
            return range(len(data['children']))

        def load_child_node(self, key):
            childdata = self.get_value()['children'][key]
            childdepth = self.get_depth() + 1
            return ServerTree.TreeNodeChannel(
                childdata, parent=self, key=key, depth=childdepth)

    class TreeWalker(urwid.ListWalker):
        """ListWalker-compatible class for displaying TreeWidgets

        positions are TreeNodes."""

        def __init__(self, trees):
            """start_from: TreeNode with the initial focus."""
            self.focus = trees[0]
            self.trees = trees
            self.focus_tree = 0

        def get_focus(self):
            widget = self.focus.get_widget()
            return widget, self.focus

        def set_focus(self, focus):
            self.focus = focus
            self._modified()

        def get_next(self, start_from):
            widget = start_from.get_widget()
            target = widget.next_inorder()
            serv = start_from.get_parent() if type(start_from) == ServerTree.TreeNodeChannel else start_from
            index = self.trees.index(serv)
            if target is None and index < len(self.trees) - 1:
                target = self.trees[index + 1].get_widget()
            if target is None:
                return None, None
            else:
                return target, target.get_node()

        def get_prev(self, start_from):
            widget = start_from.get_widget()
            target = widget.prev_inorder()
            serv = start_from.get_parent() if type(start_from) == ServerTree.TreeNodeChannel else start_from
            index = self.trees.index(serv)
            if target is None and index > 0:
                target = self.trees[index - 1].get_widget()
            if target is None:
                return None, None
            else:
                return target, target.get_node()


class Sidebar(urwid.WidgetWrap):
    def __init__(self, chat_widget: ChatWidget):
        self.chat_widget = chat_widget
        self.list_walker = urwid.SimpleListWalker([])
        self.w_listbox = urwid.ListBox(self.list_walker)
        self.update_list()
        self.__super.__init__(urwid.Padding(self.w_listbox, left=2))

    def _get_user_attr(self, member):
        if member.status == discord.Status.online:
            return "sidebar_user_on"
        if member.status == discord.Status.offline:
            return "sidebar_user_off"
        if member.status == discord.Status.idle:
            return "sidebar_user_idle"

    def mouse_event(self, size, event, button, col, row, focus):
        if event == 'mouse press':
            if button == 4:
                return self.w_listbox.keypress(size, "up") is not None
            if button == 5:
                return self.w_listbox.keypress(size, "down") is not None
        return self.w_listbox.mouse_event(size, event, button, col, row, focus)

    def keypress(self, size, key):
        if key == "esc":
            self.chat_widget.message_list.toggle_sidebar(False)
        return self.w_listbox.keypress(size, key)

    def update_list(self):

        async def callback():
            servers = set()
            memberset = set()
            for ch in self.chat_widget.channels:
                servers.add(ch.server)
            for serv in servers:
                for member in serv.members:
                    memberset.add(member)
            items = []
            on = []
            idle = []
            off = []
            for member in memberset:
                if member.status == discord.Status.online:
                    on.append(member)
                if member.status == discord.Status.offline:
                    off.append(member)
                if member.status == discord.Status.idle:
                    idle.append(member)
            members = on + idle + off
            for member in members:
                items.append(
                    urwid.AttrMap(
                        urwid.Padding(
                            urwid.Text(member.display_name), left=1, right=1),
                        self._get_user_attr(member),
                        self._get_user_attr(member)))
            self.list_walker[:] = items

        self.chat_widget.discord.loop.create_task(callback())


class SendChannelSelector(urwid.WidgetWrap):
    def __init__(self, chat_widget: ChatWidget):
        self.chat_widget = chat_widget
        self.w_cols = urwid.Columns([])
        self._selectable = True
        self.update_columns()
        self.__super.__init__(self.w_cols)

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == "left":
            self.w_cols.focus_position = (
                self.w_cols.focus_position - 1) % len(self.w_cols.widget_list)
            return
        if key == "right":
            self.w_cols.focus_position = (
                self.w_cols.focus_position + 1) % len(self.w_cols.widget_list)
            return
        if key == "enter":
            self.select_channel(self.w_cols.focus_position)
            self.chat_widget.message_list.update_columns()
            return "up"
        if key in ("delete", "d"):
            del self.chat_widget.channels[self.w_cols.focus_position]
            self.chat_widget.channel_list_updated()
            return
        return key

    def select_channel(self, index):
        self.chat_widget.send_channel = self.chat_widget.channels[index]
        self.update_columns()

    def update_columns(self):
        cols = []
        names = processing.shorten_channel_names(self.chat_widget.channels,
                                                 100)
        for ch in self.chat_widget.channels:
            if ch == self.chat_widget.send_channel:
                cols.append((urwid.AttrMap(
                    urwid.Text(
                        names[ch], align="center"),
                    "send_channel_selector_sel",
                    "send_channel_selector_sel_f"),
                             self.w_cols.options('weight', 1)))
            else:
                cols.append((urwid.AttrMap(
                    urwid.Text(
                        names[ch], align="center"),
                    "send_channel_selector",
                    "send_channel_selector_f"),
                             self.w_cols.options('weight', 1)))
        self.w_cols.contents = cols


class MessageListWidget(urwid.WidgetWrap):
    """The Listbox of MessageWidgets"""

    def __init__(self, discord_client: DiscordClient, chat_widget: ChatWidget):
        self.discord = discord_client
        self.ui = self.discord.ui
        self.chat_widget = chat_widget
        self.list_walker = MessageListWalker(self)
        self.listbox = urwid.ListBox(self.list_walker)
        self.discord.add_event_handler('on_message', self._on_message)
        self.discord.add_event_handler('on_message_edit',
                                       self._on_message_edit)
        self.discord.add_event_handler('on_message_delete',
                                       self._on_message_delete)
        self.scroll_to_bottom()
        self.w_sidebar = Sidebar(chat_widget)
        self.w_columns = urwid.Columns([('weight', 1, self.listbox)])
        self.__super.__init__(self.w_columns)

    def add_message(self, message: Message):
        self.list_walker.append(
            MessageWidget(self.discord, self.chat_widget, message))
        focus_status, focus = self.list_walker.get_focus()
        if not focus > len(self.list_walker) - 2:
            self.scroll_to_bottom()
        self.discord.ui.draw_screen()

    def _on_message(self, message: Message):
        if message.channel in self.chat_widget.channels:
            self.add_message(message)

    def _on_message_edit(self, before: Message, after: Message):
        if before.channel in self.chat_widget.channels:
            for mw in self.list_walker:
                if before.id == mw.message.id:
                    index = self.list_walker.index(mw)
                    self.list_walker[index] = MessageWidget(
                        self.discord, self.chat_widget, after)
                    break

    def _on_message_delete(self, m: Message):
        if m.channel in self.chat_widget.channels:
            for mw in self.list_walker:
                if m.id == mw.message.id:
                    self.list_walker.remove(mw)
                    break

    def scroll_to_bottom(self):
        if len(self.list_walker) > 0:
            self.listbox.set_focus(len(self.list_walker) - 1)

    def keypress(self, size, key):
        key = self._w.keypress(size, key)
        if key == "b":
            self.toggle_sidebar(True)
            return
        return key

    def mouse_event(self, size, event, button, col, row, focus):
        if event == 'mouse press':
            if button == 4:
                return self.listbox.keypress(size, "up") is not None
            if button == 5:
                return self.listbox.keypress(size, "down") is not None
        return self.listbox.mouse_event(size, event, button, col, row, focus)

    def update_columns(self):
        for mw in self.list_walker:
            mw.update_columns()

    def toggle_sidebar(self, vis):
        if vis:
            self.w_columns.contents = [
                (self.listbox, self.w_columns.options('weight', 1)),
                (self.w_sidebar, self.w_columns.options('weight', .25)),
            ]
            self.w_columns.focus_position = 1
        else:
            self.w_columns.contents = [
                (self.listbox, self.w_columns.options('weight', 1)),
            ]
            self.w_columns.focus_position = 0


class MessageListWalker(urwid.MonitoredFocusList, urwid.ListWalker):
    def __init__(self, list_widget: MessageListWidget):
        self.list_widget = list_widget
        self.is_polling = False
        self.top_reached = False
        urwid.MonitoredFocusList.__init__(self, [])
        self.get_logs(callback=list_widget.scroll_to_bottom)

    def get_logs(self, before=None, callback=lambda: None):
        if before == None and len(self) > 0:
            before = self[0].message.timestamp
        if self.is_polling or self.top_reached:
            self.list_widget.ui.notify("testytest")
            return
        self.is_polling = True

        async def _callback():
            messages = []
            for channel in self.list_widget.chat_widget.channels:
                async for m in self.list_widget.discord.logs_from(
                    channel, before=before):
                    messages.append(
                        MessageWidget(self.list_widget.discord,
                                      self.list_widget.chat_widget, m))
            if messages == [] and len(
                    self.list_widget.chat_widget.channels) > 0:
                self.top_reached = True
                messages = [TopReachedWidget(self.list_widget.chat_widget)]
            self[0:0] = messages
            self.sort_messages()
            self._modified()
            self.is_polling = False
            callback()

        self.list_widget.discord.async(_callback())

    def sort_messages(self):
        st = []
        for mw in self:
            if mw.message.id in st:
                self.remove(mw)
            else:
                st.append(mw.message.id)
        self.sort(key=lambda mw: mw.message.timestamp)

    def invalidate(self):
        self[:] = []
        self.get_logs(callback=self.list_widget.scroll_to_bottom)

    def _modified(self):
        if self.focus is not None:
            if self.focus >= len(self):
                self.focus = max(0, len(self) - 1)
        urwid.ListWalker._modified(self)

    def set_modified_callback(self, callback):
        """
        This function inherited from MonitoredList is not
        implemented in SimpleFocusListWalker.

        Use connect_signal(list_walker, "modified", ...) instead.
        """
        raise NotImplementedError('Use connect_signal('
                                  'list_walker, "modified", ...) instead.')

    def set_focus(self, position):
        """Set focus position."""
        try:
            if position < 0:
                self.get_logs()
                return
            if position >= len(self):
                raise ValueError
        except (TypeError, ValueError):
            raise IndexError("No widget at position %s" % (position, ))
        self.focus = position
        self._modified()

    def next_position(self, position):
        """
        Return position after start_from.
        """
        if len(self) - 1 <= position:
            raise IndexError
        return position + 1

    def prev_position(self, position):
        """
        Return position before start_from.
        """
        if position <= 0:
            self.get_logs()
            raise IndexError
        return position - 1

    def positions(self, reverse=False):
        """
        Optional method for returning an iterable of positions.
        """
        if reverse:
            return range(len(self) - 1, -1, -1)
        return range(len(self))


class MessageWidget(urwid.WidgetWrap):
    """A view of a message in the MessageListWidget"""

    def __init__(self, discord_client: DiscordClient, chat_widget: ChatWidget,
                 m: Message):
        self.discord = discord_client
        self.ui = self.discord.ui
        self.chat_widget = chat_widget
        self.message = m
        self.processed = processing.format_incomming(m.content)
        self.columns_w = urwid.Columns([])
        w = urwid.AttrMap(self.columns_w, None, {
            "message_timestamp": "message_timestamp_f",
            "message_channel": "message_channel_f",
            "message_author": "message_author_f",
            "message_content": "message_content_f",
            "message_channel_cur": "message_channel_cur_f",
        })
        self.update_columns()
        self.__super.__init__(w)

    def update_columns(self, author_width=13):
        author_width = author_width + 3
        channel_visible = len(self.chat_widget.channels) > 1
        channel_attr_map = "message_channel" if len(
            self.chat_widget.
            channels) > 1 and self.message.channel == self.chat_widget.send_channel else "message_channel_cur"
        self.columns = [
            self.Column(
                'timestamp',
                True, ('given', 8),
                self.message.timestamp.strftime("%H:%M"),
                attr_map="message_timestamp",
                padding=(1, 1)), self.Column(
                    'channel',
                    channel_visible, ('given', 15),
                    self.chat_widget.channel_names[self.message.channel],
                    attr_map=channel_attr_map,
                    padding=(1, 1)),
            self.Column(
                'author',
                True, ('given', author_width),
                "{0}:".format(self.message.author.name[:author_width - 1]),
                attr_map="message_author",
                padding=(1, 1)), self.Column(
                    'content',
                    True, ('weight', 1),
                    self.processed,
                    attr_map="message_content",
                    padding=(1, 1))
        ]
        visible_cols = []
        for col in self.columns:
            if col.visible:
                visible_cols.append(col)
                self.columns_w.contents = [(c.get_widget(),
                                            self.columns_w.options(
                                                width_type=c.width[0],
                                                width_amount=c.width[1]))
                                           for c in visible_cols]

    def selectable(self) -> bool:
        return True

    def keypress(self, size, key: str):
        if key == "enter" and self.message.author == self.discord.user:
            self.chat_widget.edit_message.edit_message(self.message)
            self.chat_widget.frame.set_focus(self.chat_widget.edit_message)
            return
        if key == "delete" and (self.message.author == self.discord.user or
                                self.message.channel.permissions_for(
                                    self.discord.user).manage_messages):
            self.discord.async(self.discord.delete_message(self.message))
            return
        if key == "r":
            self.chat_widget.edit_message.reply_to(self.message)
            self.chat_widget.frame.set_focus(self.chat_widget.edit_message)
            return
        return key

    class Column:
        def __init__(self,
                     name,
                     visible,
                     width,
                     content,
                     attr_map="body",
                     padding=(0, 0),
                     align="left"):
            self.name = name
            self.visible = visible
            self.width = width
            self.content = content
            self.attr_map = attr_map
            self.padding = padding
            self.align = align

        def get_widget(self):
            txt = urwid.Text(self.content, align=self.align)
            if self.padding[0] > 0 or self.padding[1] > 0:
                txt = urwid.Padding(
                    txt, left=self.padding[0], right=self.padding[1])
            return urwid.AttrMap(txt, self.attr_map)


class MessageEditWidget(urwid.WidgetWrap):
    """Wrapper for Edit widget, mainly to allow capturing keypresses"""

    def __init__(self, discord_client: DiscordClient, chat_widget: ChatWidget):
        self.discord = discord_client
        self.ui = self.discord.ui
        self.chat_widget = chat_widget
        self.editing = None
        self.caption = urwid.Text("\n Send ")
        self.edit = urwid.Edit(multiline=True)
        lb = urwid.LineBox(urwid.Padding(self.edit, left=1, right=1))
        w = urwid.Columns([('pack', self.caption), ('weight', 1, lb)])
        self.__super.__init__(w)

    def selectable(self) -> bool:
        # This is where we can disable the edit widget
        # if the user is missing permissions
        return True

    def _send_message(self):
        if self.edit.edit_text == "":
            self.stop_edit()
            return
        if self.editing is not None:
            self.discord.async(
                self.discord.edit_message(self.editing, self.edit.edit_text))
            self.stop_edit()
        else:
            self.discord.async(
                self.discord.send_message(self.chat_widget.send_channel,
                                          self.edit.edit_text))

    def keypress(self, size, key):
        if key == "enter":
            self._send_message()
            self.edit.set_edit_text("")
            return
        elif key == "meta enter":
            self.edit.keypress(size, "enter")
            return
        else:
            key = self.edit.keypress(size, key)
            if key is None:
                if self.editing is None:
                    self.discord.async(self.discord.send_typing(self.chat_widget.send_channel))
                return
            if key == "up":
                self.chat_widget.message_list.scroll_to_bottom()
            if key == "esc":
                if self.editing is not None:
                    self.stop_edit()
                    return
                else:
                    self.chat_widget.frame.edit_message.set_focus(
                        self.chat_widget.message_list)
                    return
            return key

    def edit_message(self, message: Message):
        self.caption.set_text("\n Edit ")
        self.editing = message
        self.edit.set_edit_text(message.content)
        self.edit.set_edit_pos(len(self.edit.edit_text))

    def reply_to(self, message: Message):
        self.edit.set_edit_text("> _{0}_\n".format(message.content))
        self.edit.set_edit_pos(len(self.edit.edit_text))

    def stop_edit(self):
        self.caption.set_text("\n Send ")
        self.editing = None
        self.edit.set_edit_text("")


class TopReachedWidget(urwid.WidgetWrap):
    """This widget will be displayed at the top of the channel history"""

    def __init__(self, chat_widget: ChatWidget):
        self.chat_widget = chat_widget
        self.message = FakeMessage()
        self._selectable = False
        txt = urwid.Text(
            """

        
 _____                        
< moo >                       
 -----                        
        \   ^__^              
         \  (oo)\_______      
            (__)\       )\/\  
                ||----w |     
                ||     ||     

        
Congratiulations! You have reached the top, Thats awesome! Unless the channel is empty, in which case, meh... big deal.\n\n""",
            align=urwid.CENTER)
        w = urwid.Padding(txt, left=5, right=5)
        self.__super.__init__(w)


class FakeMessage:
    """Very much a temporary thing"""

    def __init__(self):
        self.timestamp = datetime.datetime.min
        self.id = "0"