from collections import Counter
import os
import json
import sys
import datetime
import re
import shutil
import os.path as path

from .github import GithubHelper


def timestamp():
    return datetime.datetime.utcnow().isoformat()


def json_dump(data, fp):
    return json.dump(data, fp, indent=2, sort_keys=True)


def json_dumps(data):
    return json.dumps(data, indent=2, sort_keys=True)


class Error(Exception):
    pass


class NotLoaded(dict):
    pass


NOTLOADED = NotLoaded()


class Meta(object):
    def __init__(self, store, key, meta=NOTLOADED):
        self.store = store
        self.key = key.lower()
        self.meta = meta
        self.links = []
        self.loaded = meta is not NOTLOADED
        self.exists = False

    def __eq__(self, m):
        return self.store == m.store and self.key == m.key

    @property
    def name(self):
        return self.key.split('/')[-1]

    def copy_from(self, meta):
        self.store = meta.store
        self.key = meta.key
        self.meta = meta.meta.copy()
        self.links = meta.links[:]
        self.loaded = meta.loaded
        self.exists = meta.exists

    def rename(self, key):
        self.key = key

    def get_path(self):
        return self.store.get_path(self.key)

    def __str__(self):
        return '%s - %s' % (str(self.store), self.key)

    def load(self):
        if self.loaded:
            return True

        r = self.store.load_meta(self)
        return r

    def save(self):
        return self.store.save_meta(self)

    def has_link(self, meta):
        for link in self.links:
            if meta == link:
                return True

    def match_keywords(self, keywords):
        if not isinstance(keywords, (tuple, list, set)):
            keywords = [keywords]

        _keywords = [i.lower() for i in re.split(
            '\W+', '%s %s' % (self.name, self.meta.get('description', '')))]
        return len(set(keywords) & set(_keywords)) > 0

    def match_patterns(self, patterns):
        if not isinstance(patterns, (tuple, list, set)):
            patterns = [patterns]

        for p in patterns:
            if p.match(self.name):
                return True

        return False


class MetaStore(object):
    def __init__(self, name, root_path, linked_stores=[]):
        self.root = root_path
        self.name = name
        self.meta_name = '__meta__.json'
        self.linked_stores = linked_stores
        self.backlinked_stores = []
        self.template = {}  # Meta data template
        self.listeners = []

        for s in linked_stores:
            s.add_backlinked_store(self)

    def __str__(self):
        return self.name

    def __eq__(self, ms):
        return self.root == ms.root and self.meta_name == ms.meta_name

    def add_backlinked_store(self, store):
        self.backlinked_stores.append(store)

    def add_listener(self, cb):
        self.listeners.append(cb)

    def broadcast(self, ev, **kwargs):
        for cb in self.listeners:
            cb(ev, **kwargs)

    def get_path(self, key):
        return path.join(self.root, key)

    def get(self, key):
        m = Meta(self, key.lower())
        self.load_meta(m)
        return m

    def load_meta(self, meta):
        meta.loaded = True
        p = meta.get_path()
        if not path.isdir(p):
            return False

        _meta = {}
        links = []
        for fn in sorted(os.listdir(p)):
            fp = path.join(p, fn)
            if fn == self.meta_name:
                with open(fp, 'r') as f:
                    meta.exists = True
                    _meta.update(json.load(f))
            if path.islink(fp):
                link = self.get_linked(fp)
                if link:
                    links.append(link)
                else:
                    print '%s is a symlink but not pointing to another store' % fp
        meta.meta = _meta
        meta.links = links
        return True

    def save_meta(self, meta):
        if not meta.loaded:
            raise Error("Meta should be loaded before saving: %s" % meta)

        p = meta.get_path()

        try:
            os.makedirs(p)
        except:
            pass

        fn = path.join(p, self.meta_name)
        with open(fn, 'w') as f:
            json_dump(meta.meta, f)
        meta.exists = True

        return True

    def get_or_create(self, key, meta={}):
        key = key.lower()
        ret = self.get(key)
        if ret is None or not ret.exists:
            self.add_key(key, meta)
        return meta

    def get_linked(self, lpath):
        p = path.realpath(lpath)
        for s in self.linked_stores:
            if s.is_in_store(p):
                return s.meta_from_link(lpath)

        return None

    def is_in_store(self, p):
        tmp = path.relpath(p, self.root)
        if tmp.startswith('../'):
            return False

        return True

    def meta_from_link(self, lpath):
        p = path.realpath(lpath)
        key = path.relpath(p, self.root)
        key = key.lower()
        return Meta(self, key)

    def add_link(self, key, lpath, name=None, create=False):
        key = key.lower()
        if isinstance(lpath, Meta):
            lpath = lpath.get_path()

        name = name and name or path.basename(lpath)
        p = self.get_path(key)
        if not path.isdir(p):
            if not create:
                return False  # key doesn't exist
            self.add_key(key)
        lpath = path.relpath(lpath, p)
        p = path.join(p, name)
        if path.islink(p):
            return False  # already there
        os.symlink(lpath, p)
        self.update_timestamp(key)

        self.broadcast('add_link')
        return True

    def remove_link(self, key, lpath):
        key = key.lower()
        if isinstance(lpath, Meta):
            lpath = lpath.get_path()

        name = lpath.split('/')[-1]
        p = self.get_path(key)
        p = path.join(p, name)
        if path.islink(p):
            os.unlink(p)
            self.update_timestamp(key)
            self.broadcast('remove_link')
            return True
        elif not path.exists(p):
            return True
        return False

    def add_key(self, key, meta={}):
        key = key.lower()
        p = self.get_path(key)
        fn = path.join(p, self.meta_name)
        if path.isfile(fn):
            return False  # Already exists

        _meta = self.template.copy()
        _meta.update(meta)
        now = timestamp()
        _meta['created_at'] = now
        _meta['updated_at'] = now

        m = Meta(self, key, _meta)
        m.save()

        self.broadcast('add_key')

        return m

    def remove_key(self, key):
        key = key.lower()
        m = key
        if not isinstance(m, Meta):
            m = self.get(key)

        if not m:
            return False

        for s in self.backlinked_stores:
            for key2 in s.find_links([m]):
                s.remove_link(key2, m)

        if m.exists:
            shutil.rmtree(m.get_path())

        self.broadcast('remove_key')

        return True

    def rename_key(self, key, new_key):
        key = key.lower()
        new_key = new_key.lower()
        m = key
        if not isinstance(m, Meta):
            m = self.get(key)

        if not m or not m.exists:
            raise Error('Key %s doesn\'t exist' % key)

        nm = Meta(self, new_key)
        nm.load()
        if not nm or not nm.exists or nm.key != new_key:  # In case the loader uses fuzz load
            nm = Meta(self, new_key)
            nm.copy_from(m)
            nm.rename(new_key)
            nm.meta['updated_at'] = timestamp()
            nm.save()

        for s in self.backlinked_stores:
            for key2 in s.find_links([m]):
                r = s.remove_link(key2, m)
                repo = s.get(key2)
                if not repo.has_link(nm):
                    r = s.add_link(key2, nm) and r
                if not r:
                    raise Error(
                        "Unable to change link from %s to %s for key %s" %
                        (key, new_key, key2))

        shutil.rmtree(m.get_path())

        self.broadcast('rename_key')

        return True

    def update_timestamp(self, key):
        meta = self.get(key)
        if not meta.exists:
            return False

        meta.meta['updated_at'] = timestamp()
        return meta.save()

    def keys(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            if self.meta_name in filenames:
                yield path.relpath(dirpath, self.root)

    def find_links(self, links):
        link_names = set(i.key.split('/')[-1] for i in links)

        for dirpath, dirnames, filenames in os.walk(self.root):
            if self.meta_name in filenames and len(
                    link_names & set(dirnames)) == len(link_names):
                ret = True
                for link in links:
                    lpath = path.join(dirpath, link.name)
                    meta = self.get_linked(lpath)
                    if not meta == link:
                        ret = False
                        break
                if ret:
                    yield path.relpath(dirpath, self.root)

    def find_keywords(self, keywords):
        for key in self.keys():
            m = self.get(key)
            if m.match_keywords(keywords):
                yield key

    def key_hints(self, prefix):
        p = self.get_path(prefix)
        if path.isdir(p):
            return os.listdir(p)
        return []

    def link_stats(self):
        stats = Counter()
        for key in self.keys():
            m = self.get(key)
            for link in m.links:
                stats[link.key] += 1

        links = stats.most_common()
        return links

    def validate(self):
        errors = []
        torename = set()
        stats = Counter()
        for key in self.keys():
            m = self.get(key)
            stats['total'] += 1
            if re.search(r'[A-Z]', key):
                levels = key.split('/')
                for i in xrange(1, len(levels) + 1):
                    _p = '/'.join(levels[:i])
                    if re.search(r'[A-Z]', levels[i - 1]):
                        torename.add(_p)
                m.key = key
                m.loaded = False
                m.load()
                print >> sys.stderr, 'Warning: update key to lower case: %s' % key

            if not m or not m.exists:
                errors.append("Key doesn't exist or load: %s" % key)

            for link in m.links:
                stats['links'] += 1
                link.load()
                if not link or not link.exists:
                    errors.append("Link doesn't exist or load for key %s: %s" %
                                  (key, link))

            changed = False
            if 'created_at' not in m.meta:
                m.meta['created_at'] = timestamp()
                changed = True
                print >> sys.stderr, "Warning: created_at created for %s" % key

            if 'updated_at' not in m.meta:
                m.meta['updated_at'] = timestamp()
                changed = True
                print >> sys.stderr, "Warning: updated_at created for %s" % key

            if changed:
                stats['fixed'] += 1
                m.save()

            if len(errors) > 50:
                errors.append('Too many errors')
                break

        if torename:
            keys = sorted(torename)
            skipped = set()
            stats['renamed'] += len(keys)
            for old in keys:
                name = path.basename(old)
                p = path.dirname(old).lower()
                old = path.join(p, name)
                new = path.join(p, name.lower())
                _old = self.get_path(old)
                _new = self.get_path(new)
                if p in skipped:
                    errors.append(
                        "Unable to rename %s to %s due to the failure above" %
                        (old, new))
                    continue
                if path.exists(_new):
                    skipped.add(new)
                    errors.append(
                        "Unable to rename %s to %s. The latter already exists" %
                        (old, new))
                    continue

                os.rename(_old, _new)

        if errors:
            raise Error('\n'.join(errors))

        return stats


class CachedMetaStore(MetaStore):
    def __init__(self, *args, **kwargs):
        super(CachedMetaStore, self).__init__(*args, **kwargs)
        #print >>sys.stderr, 'Loading', self.name
        self._cache = {}
        self.cache_all()
        #print >>sys.stderr, 'Loaded', self.name

    def keys(self):
        return self._cache.keys()

    def cache_all(self):
        for key in super(CachedMetaStore, self).keys():
            self.cache(key)

    def cache(self, key):
        key = key.lower()
        meta = Meta(self, key)
        MetaStore.load_meta(self, meta)
        if meta.exists:
            self._cache[key] = meta
        elif key in self._cache:
            del self._cache[key]
        return meta

    def load_meta(self, meta):
        m = self._cache.get(meta.key, None)
        if not m:
            m = self.cache(meta.key)

        if m:
            meta.copy_from(m)

        return True

    def _key_change_wrapper(func_name):
        def _wrapped(self, key, *args, **kwargs):
            key = key.lower()
            obj = super(CachedMetaStore, self)
            func = getattr(obj, func_name)
            ret = func(key, *args, **kwargs)
            if ret:
                self.cache(key)
            return ret

        return _wrapped

    add_key = _key_change_wrapper('add_key')
    remove_key = _key_change_wrapper('remove_key')
    rename_key = _key_change_wrapper('rename_key')
    remove_link = _key_change_wrapper('remove_link')
    add_link = _key_change_wrapper('add_link')


class UniqueCachedMetaStore(CachedMetaStore):
    def __init__(self, *args, **kwargs):
        self._cache_unique = {}
        super(UniqueCachedMetaStore, self).__init__(*args, **kwargs)

    def get_unique_key(self, key):
        if key:
            key = key.split('/')[-1].lower()
        return key

    def cache(self, key):
        key = key.lower()
        meta = super(UniqueCachedMetaStore, self).cache(key)
        uk = self.get_unique_key(key)
        if meta.exists:
            self._cache_unique[uk] = meta
        elif uk in self._cache_unique:
            tmp = self._cache_unique[uk]
            if tmp.key == key:
                del self._cache_unique[uk]

        return meta

    def load_meta(self, meta):
        m = self._cache.get(meta.key, None)
        if not m:
            if self.get_unique_key(meta.key) == meta.key:
                m = self._cache_unique.get(meta.key, None)
            if not m:
                m = self.cache(meta.key)

        if m:
            meta.copy_from(m)

        return True

    def add_key(self, key, meta={}):
        tmp = self._cache_unique.get(self.get_unique_key(key), None)
        if tmp and tmp.key != key:
            raise Error(
                "Can't add key because it's not unique: %s. The one exists: %s" %
                (key, tmp.key))

        if self.get_unique_key(key) == key:
            raise Error("You must add a tag with its full name ex. domain/name")

        return super(UniqueCachedMetaStore, self).add_key(key, meta)

    def key_hints(self, prefix):
        ret = []
        if not prefix:
            ret = self._cache_unique.keys()

        ret += super(UniqueCachedMetaStore, self).key_hints(prefix)
        return ret

    def validate(self):
        keys = [(self.get_unique_key(i), i) for i in self._cache.keys()]
        c = Counter([i[0] for i in keys])
        tmp = c.most_common()
        duplicates = [i[0] for i in filter(lambda x: x[1] > 1, tmp)]
        if duplicates:
            ret = {}
            for i in keys:
                if i[0] in duplicates:
                    tmp = ret.setdefault(i[0], [])
                    tmp.append(i[1])

            raise Error('Duplicate keys %s' % json_dumps(ret))

        return super(UniqueCachedMetaStore, self).validate()


class GithubMetaStore(MetaStore):
    def add_key(self, key, meta={}):
        key = key.lower()
        if not meta:
            # fetch meta
            print >> sys.stderr, 'Fetching meta from Github: %s' % key
            gh = GithubHelper()
            data = gh.get_repo(key)
            meta = gh.compact(data)
        return super(GithubMetaStore, self).add_key(key, meta)
