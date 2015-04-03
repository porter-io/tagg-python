#!/usr/bin/env python
import os
import json
import sys
import re
import os.path as path
import argparse

from tagg import *


def list_print(l):
    for i in l:
        print i


def meta_print(m, load=True):
    if load:
        m.load()
        if not m.exists:
            print m, 'doesn\'t exist'
            return

    print m.store, '-', m.key
    print 'Exists:', m.exists, 'Loaded:', m.loaded
    print json_dumps(m.meta)
    print 'Links:'
    print list_print(m.links)


class ConfirmSession(object):
    def __init__(self, remember=True):
        self.history = {}
        self.remember = remember

    def confirm(self, msg):
        r = self.history.get(msg, None)
        if r is not None:
            return r

        y = raw_input(msg + '? (default yes)')
        r = y.lower() in ('y', 'yes', 'ok', '')

        if self.remember:
            self.history[msg] = r
        return r

    def repo_confirm(self, msg, repo):
        r = self.history.get(msg, None)
        if r is not None:
            return r

        while r is None:
            y = raw_input(
                msg + '? (default yes, type detail or d to show repo details)')
            r = y.lower() in ('y', 'yes', 'ok', '')
            if y.lower() in ('details', 'd'):
                meta_print(repo)
                r = None
            else:
                break

        if self.remember:
            self.history[msg] = r
        return r


class NoConfirmSession(object):
    def confirm(self, msg):
        print msg
        return True

    def repo_confirm(self, msg, repo):
        print msg
        return True

# REPL
try:
    from prompt_toolkit.contrib.regular_languages.compiler import compile
    from prompt_toolkit.contrib.regular_languages.completion import GrammarCompleter
    from prompt_toolkit.contrib.regular_languages.lexer import GrammarLexer
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.contrib.shortcuts import get_input
    from prompt_toolkit.contrib.completers import WordCompleter
    from pygments.styles import get_style_by_name
    from pygments.style import Style
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import get_formatter_by_name
    from pygments.token import Token
    from pygments import highlight

    class REPLStyle(Style):
        background_color = None
        styles = {
            Token.Placeholder: "#888888",
            Token.Placeholder.Variable: "#888888",
            Token.Placeholder.Bracket: "bold #ff7777",
            Token.Placeholder.Separator: "#ee7777",
            Token.Aborted: '#aaaaaa',
            Token.Prompt.BeforeInput: 'bold',
            Token.Operator: '#33aa33 bold',
            Token.Number: '#aa3333 bold',
            Token.Menu.Completions.Completion.Current: 'bg:#00aaaa #000000',
            Token.Menu.Completions.Completion: 'bg:#008888 #ffffff',
            Token.Menu.Completions.ProgressButton: 'bg:#003333',
            Token.Menu.Completions.ProgressBar: 'bg:#00aaaa',
        }

    def create_grammar():
        return compile("""
            (\s* 
            repos \s (?P<repocmd>tag|untag) \s (?P<repokey>[\w/\-\._]*) \s (?P<tagkey>[\w/\-\._]*)(,(?P<tagkey>[\w/\-\._]*))* | 
            repos \s (?P<repocmd>links) \s (?P<tagkey>[\w/\-\._]*)(,(?P<tagkey>[\w/\-\._]*))* |
            repos \s (?P<repocmd>add|show|remove|edit|rename) \s (?P<repokey>[\w/\-\._]*) |
            tags \s (?P<tagcmd>add|show|remove|edit|rename) \s (?P<tagkey>[\w/\-\._]*) 
            )
        """)

    json_lexer = get_lexer_by_name('json')
    formatter = get_formatter_by_name(
        'terminal' if not os.environ.get('TERM', '').find('256') > 0 else
        'terminal256')

    def meta_print(m, load=True):
        if load:
            m.load()
            if not m.exists:
                print m, 'does\'t exist'
                return

        print m.store, '-', m.key
        print 'Exists:', m.exists, 'Loaded:', m.loaded
        print highlight(json_dumps(m.meta),
                        lexer=json_lexer,
                        formatter=formatter)
        print 'Links:'
        print list_print(m.links)

    class CustomCompleter(Completer):
        def __init__(self, func):
            self.func = func

        def get_completions(self, document, complete_event):
            w = document.text_before_cursor
            for i in self.func(w):
                yield Completion(i, -len(w))

    class CachedHints(object):
        def __init__(self, store):
            self.store = store
            self.store.add_listener(self.on_change)
            self.cache = {}

        def on_change(self, ev, **kwargs):
            if ev in ('add_key', 'remove_key', 'rename_key'):
                self.cache = {}

        def __call__(self, prefix):
            if len(prefix) < 1:
                return []
            o = path.dirname(prefix)
            name = path.basename(prefix)
            dirs = self.cache.get(o, [])
            if not dirs:
                dirs = self.cache[o] = self.store.key_hints(o)

            ret = []
            for i in dirs:
                if i.startswith(name):
                    ret.append(path.join(o, i))

            return ret

    class TagCli(object):
        def __init__(self, targets, parser):
            self.targets = targets
            self.parser = parser

        def run(self):
            default_style = get_style_by_name('default')
            g = create_grammar()
            lexer = GrammarLexer(g,
                                 tokens={
                                     "repokey": Token.Name,
                                     "tagkey": Token.Name,
                                     "repocmd": Token.Operator,
                                     "tagcmd": Token.Operator
                                 })
            hinters = {
                'repos': CachedHints(self.targets['repos']),
                'tags': CachedHints(self.targets['tags'])
            }
            completer = GrammarCompleter(g, {
                'repocmd': WordCompleter(repo_cmds),
                'tagcmd': WordCompleter(cmds),
                'repokey': CustomCompleter(hinters['repos']),
                'tagkey': CustomCompleter(hinters['tags']),
            })
            while True:
                try:
                    text = get_input('> ',
                                     style=REPLStyle,
                                     completer=completer,
                                     history_filename='./.tag_history')
                    if text == 'exit':
                        break
                    elif text.startswith('help'):
                        self.parser.print_help()
                        continue

                    args = [i.strip() for i in text.split(' ', 3)]
                    process_cmd(self.targets, *args)

                except (KeyboardInterrupt, Exception), e:
                    print e
                    print
except ImportError, e:
    TagCli = None


# Cli Core
def process_cmd(targets, cmd,
                subcmd=None,
                key=None,
                value=None,
                confirm_session=None):
    target = None
    cs = confirm_session or ConfirmSession()
    target = targets.get(cmd, None)
    tagstore = targets.get('tags', None)
    repostore = targets.get('repos', None)

    # in case key is a path
    if key and path.isdir(key) and target.is_in_store(key):
        key = target.meta_from_link(key).key

    if subcmd == 'list':
        list_print(target.keys())
    elif subcmd == 'links':
        if not key:
            raise Error('a key or multiple keys separated by , is required')

        tags = []
        for i in key.split(','):
            tag = tagstore.get(i)
            if not tag or not tag.exists:
                raise Error("Tag %s doesn\'t exist")
            tags.append(tag)
        list_print(repostore.find_links(tags))
    elif subcmd == 'add':
        if not key:
            raise Error('a key is required')
        meta = {}
        if value:
            meta = json.loads(value)
        if target.add_key(key, meta):
            print 'Added', key
        else:
            print 'Add failed. Probably already existed.'
    elif subcmd == 'remove':
        if not key:
            raise Error('a key is required')
        if target.remove_key(key):
            print 'Removed', key
        else:
            print 'Remove failed. Probably doesn\'t exist.'
    elif subcmd == 'find':
        if not key:
            raise Error('a keyword or a list of , separated keywords are required')
        list_print(target.find_keywords([i.strip() for i in key.split(',')]))
    elif subcmd == 'rename':
        if not key or not value:
            raise Error('there must be a key and a new key')
        if target.rename_key(key, value):
            print 'Renamed key %s to %s' % (key, value)
        else:
            print 'Rename key %s to %s failed. Probably doesn\'t exist.' % (
                key, value)
    elif subcmd == 'show':
        if not key:
            raise Error('a key is required')
        m = target.get(key)
        meta_print(m)
    elif subcmd == 'tag' and target is repostore:
        if not value:
            raise Error('a tag is required')
        tags = [i.strip() for i in value.split(',')]
        for i in value.split(','):
            i = i.strip()
            tag = tagstore.get(i)
            if not tag or not tag.exists:
                if not cs.confirm('Tag %s doesn\'t exist. Create' % i):
                    raise Error('Tag doesn\'t exist: %s. Abort' % value)
                tag = tagstore.add_key(i)
            if not tag:
                raise Error('Tag %s doesn\'t exist')
            if repostore.add_link(key, tag):
                print 'Added link', tag, 'to', key
            else:
                print 'Can\'t add link', tag, 'to', key, 'Proabably already existed'
    elif subcmd == 'untag' and target is repostore:
        if not value:
            raise Error('a tag is required')
        tagname = value.split('/')[-1]
        if repostore.remove_link(key, tagname):
            print 'Removed link', tagname, 'from', key
        else:
            print 'Removed link', tagname, 'from', key, 'failed. Probably already removed'
    elif subcmd == 'edit':
        if not key:
            raise Error('a key is required')
        p = target.get(key)
        fn = path.join(p.get_path(), target.meta_name)
        os.system('vim %s' % fn)
    elif subcmd == 'validate':
        print target.validate()
        print 'Done'
    elif subcmd == 'link_stats':
        stats = target.link_stats()
        print ', '.join(['%s(%d)' % (i[0], i[1]) for i in stats])
    elif cmd == 'export':
        repos = {}
        for key in repostore.keys():
            repo = repostore.get(key)
            m = repo.meta.copy()
            m['tags'] = [i.key for i in repo.links]
            repos[key] = m

        tags = {}
        for key in tagstore.keys():
            tags[key] = tagstore.get(key).meta

        data = {'repos': repos, 'tags': tags}
        print json_dumps(data)
    else:
        raise Error('Unknown cmd %s' % cmd)


cmds = ['list', 'add', 'remove', 'rename', 'show', 'edit', 'validate', 'links',
        'find', 'link_stats']
repo_cmds = cmds + ['tag', 'untag']


def get_targets(data_dir='.'):
    tagstore = UniqueCachedMetaStore('Tags', path.join(data_dir, 'tags'))
    repostore = GithubMetaStore('Github Repos', path.join(data_dir, 'repos'),
                                linked_stores=[tagstore])
    targets = {'tags': tagstore, 'repos': repostore, }
    return targets


def main():
    parser = argparse.ArgumentParser(
        description='Shortcut functions to manipulate tags and repos')
    parser.add_argument('-d', '--data-dir',
                        help='Set the data dir',
                        default='./')
    parser.add_argument('--force',
                        action='store_true',
                        help='Force operate in an empty data dir',
                        default=False)
    subs = parser.add_subparsers()

    rp = subs.add_parser('repos')
    rp.add_argument('subcmd', nargs='?', choices=repo_cmds, default='list')
    rp.add_argument('key', nargs='?')
    rp.add_argument('value', nargs='?')
    rp.set_defaults(cmd='repos')

    tp = subs.add_parser('tags')
    tp.add_argument('subcmd', nargs='?', choices=cmds, default='list')
    tp.add_argument('key', nargs='?')
    tp.add_argument('value', nargs='?')
    tp.set_defaults(cmd='tags')

    ep = subs.add_parser('export')
    ep.set_defaults(cmd='export')
    ep.add_argument('subcmd', nargs='?')
    ep.add_argument('key', nargs='?')
    ep.add_argument('value', nargs='?')

    ep = subs.add_parser('shell')
    ep.set_defaults(cmd='shell')
    ep.add_argument('subcmd', nargs='?')
    ep.add_argument('key', nargs='?')
    ep.add_argument('value', nargs='?')
    stdin = ''
    if not sys.stdin.isatty():
        stdin = sys.stdin.readlines()
        if len(sys.argv) > 1:
            # Piped arguments
            r = sys.argv[:]
            if not '%' in r:
                raise Error(
                    'You need to specify a %% mark to use partial arguments')
            pos = r.index('%') - 1
            for line in stdin:
                if line.startswith('#'):
                    continue
                r = sys.argv[1:]
                r[pos] = line.strip()
                args = parser.parse_args(r)
                targets = get_targets(args.data_dir)
                process_cmd(targets, args.cmd, args.subcmd, args.key,
                            args.value, NoConfirmSession())
        else:
            # Piped cmds
            for line in stdin:
                if line.startswith('#'):
                    continue
                args = parser.parse_args([i.strip()
                                          for i in re.split(r'\s+', line, 3)])
                targets = get_targets(args.data_dir)
                process_cmd(targets, args.cmd, args.subcmd, args.key,
                            args.value, NoConfirmSession())
        sys.exit(0)

    args = parser.parse_args()
    targets = get_targets(args.data_dir)
    if not path.exists(targets['tags'].root) and not path.exists(
        targets['repos'].root) and not args.force:
        raise Error(
            "%s doesn't seem to have any data in it. Use --force to operate in it."
            % args.data_dir)

    if args.cmd == 'shell':
        # Enter REPL
        if TagCli:
            TagCli(targets, parser).run()
        else:
            print "You have to install prompt_toolkit & pygments to use REPL mode"
        sys.exit(0)

    # Run cmd n quit
    process_cmd(targets, args.cmd, args.subcmd, args.key, args.value)


if __name__ == '__main__':
    main()
