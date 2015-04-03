#!/usr/bin/env python
import sys
import json
import re
import argparse
import os
from collections import Counter
from itertools import imap

from . import cli as _tag


class ImmediateActions(object):
    def __init__(self, interactive=True):
        self.show_skipped_repos = True
        self.interactive = interactive
        self.cs = _tag.ConfirmSession()

    def get_tag(self, tagstore, key):
        return tagstore.get(key)

    def get_repo(self, store, key):
        return store.get(key)

    def tag_repo(self, repostore, repo, tag):
        if not self.interactive or self.cs.repo_confirm('Tag %s as %s' %
                                                        (repo, tag), repo):
            repostore.add_link(repo.key, tag)
            return True

        return False

    def new_tag(self, tagstore, key, meta={}):
        if not self.interactive or self.cs.confirm('Create tag %s' % (key, )):
            return tagstore.add_key(key, meta)

        return None

    def new_repo(self, repostore, key, meta={}):
        if not self.interactive or self.cs.confirm('Create repo %s' % (key, )):
            return repostore.add_key(key, meta)

        return None

    def new_comment(self, msg):
        print '#', msg

    def repo_not_tagged(self, repostore, repo):
        pass

    def on_finish(self, c):
        pass


class SuggestActions(object):
    def __init__(self):
        self.show_skipped_repos = True
        self.tag_actions = []
        self.repo_actions = []
        self.suggested_tags = {}
        self.suggested_repos = {}

    def get_tag(self, tagstore, key):
        t = tagstore.get(key)
        if not t or not t.exists:
            t = self.suggested_tags.get(key)

        return t

    def get_repo(self, repostore, key):
        t = repostore.get(key)
        if not t or not t.exists:
            t = self.suggested_repos.get(key)

        return t

    def tag_repo(self, repostore, repo, tag):
        self.repo_actions.append('repos\ttag\t%s\t%s' % (repo.key, tag.key))
        return True

    def new_tag(self, tagstore, key, meta={}):
        self.tag_actions.append('tags\tadd\t%s\t%s' % (key, json.dumps(meta)))
        # Fake tag
        tag = _tag.Meta(tagstore, key, meta)
        tag.exists = True
        self.suggested_tags[key] = tag
        return tag

    def new_repo(self, repostore, key, meta={}):
        self.repo_actions.append('repos\tadd\t%s\t%s' %
                                 (key, json.dumps(meta)))
        # Fake tag
        repo = _tag.Meta(repostore, key, meta)
        repo.exists = True
        self.suggested_repos[key] = repo
        return repo

    def repo_not_tagged(self, repostore, repo):
        if not self.show_skipped_repos:
            return
        tags = [i.name for i in repo.links]
        self.new_comment('No tag detected for repo %s. Already have tags %s' %
                         (repo.key, ','.join(tags)))
        self.new_comment('repos\ttag\t%s\t\t\t' % repo.key)

    def new_comment(self, msg):
        self.repo_actions.append('# ' + msg)

    def on_finish(self, c):
        _tag.list_print(self.tag_actions)
        _tag.list_print(self.repo_actions)


class AutoTagger(object):
    def __init__(self, tagstore, repostore, actions):
        self.tag_language = False
        self.tag_original = False
        self.tagstore = tagstore
        self.repostore = repostore
        self.actions = actions

    def normalize_tag_name(self, s):
        return re.sub(r'[\s]+', '-', s.lower().strip())

    def autotag_repo(self, repo, definitions):
        tagged = False
        tagged_tags = set()
        c = Counter()
        key = repo.key
        tmp = key.split('/')
        name = tmp[-1]
        account = tmp[-2]

        def _tag_helper(tag_key, allow_alternative=False):
            if tag_key in tagged_tags:
                return True

            tag = self.actions.get_tag(self.tagstore, tag_key)
            if allow_alternative:
                tag_key = self.tagstore.get_unique_key(tag_key)
                tag = self.actions.get_tag(self.tagstore, tag_key)

            if not tag or not tag.exists:
                tag = self.actions.new_tag(self.tagstore, tag_key)
                if tag:
                    c['new_tag'] += 1

            if tag and not repo.has_link(tag):
                if self.actions.tag_repo(self.repostore, repo, tag):
                    tagged_tags.add(tag_key)
                    c['new_link'] += 1
                    return True

            return False

        # Original
        fork = repo.meta.get('fork', None)
        if self.tag_original and fork is False:
            tagged = _tag_helper('general/original') or tagged

        # Language
        language = repo.meta.get('language', '')
        if self.tag_language and language:
            tag_name = "language/" + self.normalize_tag_name(language)
            tagged = _tag_helper(tag_name, True) or tagged

        # Keywords
        for tag_name, v in definitions.get('keywords', {}).iteritems():
            if v['tag'].key in tagged_tags or repo.has_link(v['tag']):
                continue

            if v['plainwords'] and repo.match_keywords(v['plainwords']):
                if self.actions.tag_repo(self.repostore, repo, v['tag']):
                    c['new_link'] += 1
                    tagged = True
                continue

            if v['patterns'] and repo.match_patterns(v['patterns']):
                if self.actions.tag_repo(self.repostore, repo, v['tag']):
                    c['new_link'] += 1
                    tagged = True
                continue

        # Brands
        for tag_name, v in definitions.get('brands', {}).iteritems():
            if account in v:
                if tag_name.find('/') == -1:
                    tag_name = 'brand/%s' % tag_name
                tagged = _tag_helper(tag_name) or tagged
                tagged = _tag_helper('official') or tagged

        if tagged:
            c['repo_tagged'] += 1
        else:
            self.actions.repo_not_tagged(self.repostore, repo)
            c['repo_skipped'] += 1
        return c

    def compile_definitions(self, data, counter):
        keywords = {}
        for tag_name, v in data.get('keywords', {}).iteritems():
            patterns = []
            plainwords = []
            if tag_name.find('/') == -1:
                tag_name = '%s/%s' % (data.get('default_type', 'general'),
                                      tag_name)
            tag = self.tagstore.get(tag_name)
            if not tag or not tag.exists:
                tag = self.actions.new_tag(self.tagstore, tag_name)
                if not tag:
                    continue
                counter['new_tag'] += 1

            for s in v:
                if s.startswith('/') and s.endswith('/'):
                    patterns.append(re.compile(s[1:-1]))
                else:
                    plainwords.append(s)

            keywords[tag_name] = {
                'tag': tag,
                'plainwords': set(plainwords),
                'patterns': patterns
            }
        compiled = data.copy()
        compiled['keywords'] = keywords
        return compiled

    def autotag(self, data, keys):
        c = Counter()
        defs = self.compile_definitions(data, c)

        print >> sys.stderr, 'Total rules defined in data:', len(
            defs.get('keywords', {})) + len(defs.get('brands', {}))
        for key in keys:
            repo = self.actions.get_repo(self.repostore, key)
            c.update(self.autotag_repo(repo, defs))

        self.actions.on_finish(c)
        return c

    def prepare_json_repos(self, repos):
        keys = set()
        for repojson in repos:
            key = repojson['full_name'].lower()
            if key in keys:
                continue
            repo = self.actions.get_repo(self.repostore, key)
            if not repo or not repo.exists:
                repo = self.actions.new_repo(self.repostore, key, repojson)
            else:
                self.actions.new_comment('Repo already exists: %s' % key)
            keys.add(key)
        return keys


def main():
    tmp = os.path.dirname(__file__)
    default_def = os.path.join(tmp, 'default_defs.json')
    parser = argparse.ArgumentParser(
        description='Automatically tag repos according to their meta data')
    parser.add_argument(
        '-d', '--data-dir',
        help='Set the data dir',
        default='./')
    parser.add_argument(
        '-r', '--run',
        action='store_true',
        default=False,
        help='Instead of just printing commands, actually take  actions')
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        default=False,
        help='Ask before every action')
    parser.add_argument(
        '--no-language',
        action='store_false',
        dest='tag_language',
        default=True,
        help='Don\'t tag the language tag')
    parser.add_argument(
        '--no-original',
        action='store_false',
        dest='tag_original',
        default=True,
        help='Don\'t tag a \'original\' tag if the repo is not a fork')
    parser.add_argument(
        '-g', '--github',
        dest='github_account',
        help='Get my repos on github and tag them')
    parser.add_argument(
        '--starred',
        action='store_true',
        help=
        'In addition of my repos on github, also get my starred repos. Must be used with -g',
        default=False)
    parser.add_argument(
        '--top1k',
        action='store_true',
        help='Get github top1k repos and tag them')
    parser.add_argument(
        '-f', '--def',
        dest='datafile',
        help='Autotagg definition file. If none provided, the default is used.',
        default=default_def)
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force operate in an empty data dir',
        default=False)
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='Tag all existing repos in the data dir',
        default=False)
    parser.add_argument(
        'repo_name',
        nargs='?',
        help='The fullname of the repo to run autotag on.')

    args = parser.parse_args()
    actions = SuggestActions()
    if args.run:
        actions = ImmediateActions(args.interactive)

    if not args.datafile and not args.tag_language and not args.tag_original:
        parser.print_help()
        print >> sys.stderr, "There's nothing to do. At least remove one of --no-language, --no-original or provide a datafile"
        sys.exit(1)

    data = {}

    if args.datafile:
        with open(args.datafile, 'r') as f:
            print >> sys.stderr, "Start tagging repos with tags defined in", args.datafile
            data = json.load(f)

    targets = _tag.get_targets(args.data_dir)
    if not os.path.exists(targets['tags'].root) and not os.path.exists(
            targets['repos'].root) and not args.force:
        print >> sys.stderr, "%s doesn't seem to have any data in it. Use --force to operate in it." % args.data_dir
        sys.exit(1)

    tagger = AutoTagger(targets['tags'], targets['repos'], actions)
    tagger.tag_language = args.tag_language
    tagger.tag_original = args.tag_original

    if args.github_account:
        print >> sys.stderr, "Fetching my repos"
        gh = _tag.GithubHelper(args.github_account)
        repos = gh.get_mine()
        if args.starred:
            repos += gh.get_starred()

        repos = imap(gh.compact, repos)
        keys = tagger.prepare_json_repos(repos)
        print >> sys.stderr, tagger.autotag(data, keys)
        print >> sys.stderr, 'Done'
    elif args.top1k:
        print >> sys.stderr, "Fetching Github top1k"
        gh = _tag.GithubHelper()
        repos = gh.get_top1k()
        if args.starred:
            repos += gh.get_starred()

        repos = imap(gh.compact, repos)
        keys = tagger.prepare_json_repos(repos)
        print >> sys.stderr, tagger.autotag(data, keys)
        print >> sys.stderr, 'Done'
    elif args.starred:
        print >> sys.stderr, "No github account is provided. Add -g"
    elif args.all:
        actions.show_skipped_repos = False
        print >> sys.stderr, tagger.autotag(data, targets['repos'].keys())
        print >> sys.stderr, 'Done'
    elif args.repo_name:
        #actions.show_skipped_repos = False
        print >> sys.stderr, tagger.autotag(data, [args.repo_name])
    else:
        print >> sys.stderr, "There's nothing to do. At least use one of -g, -a, --top1k or provide a repo_name"
        sys.exit(1)


if __name__ == '__main__':
    main()
