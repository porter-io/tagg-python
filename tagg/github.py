import requests
import sys
import time
from os import path
from urlparse import urljoin


class GithubHelper(object):
    def __init__(self, username=''):
        self.token = ''
        self.username = username
        self.api_root = 'https://api.github.com'
        self.ua = 'Tag-Github'
        self.headers = {'User-Agent': self.ua}

        if path.isfile('./.github_token'):
            with open('./.github_token', 'r') as f:
                self.token = f.read().strip()
                self.headers['Authorization'] = 'token ' + self.token

    def _get(self, _path, params=None):
        def _do(url):
            from . import Error
            r = requests.get(url, params=params, headers=self.headers)
            limit = r.headers.get('X-RateLimit-Limit', -1)
            remaining = r.headers.get('X-RateLimit-Remaining', -1)
            if limit is not None:
                print >> sys.stderr, 'Limit: %s/%s' % (remaining, limit)
            if r.status_code != 200:
                raise Error('Github returned error: %s' % r)

            data = r.json()
            if isinstance(data, dict) and 'items' in data:
                data = data['items']

            next_ = r.links and r.links.get('next', None) or None
            if remaining == '0' and next_:
                print >> sys.stderr, 'Sleeping for more quota'
                time.sleep(60)
            if not isinstance(data, list):
                data = [data]
            return data, next_

        items, next_url = _do(urljoin(self.api_root, _path))
        for i in items:
            yield i

        while next_url:
            items, next_url = _do(next_url['url'])
            for i in items:
                yield i

    def get_mine(self):
        return self._get('/users/%s/repos' % self.username)

    def get_starred(self):
        return self._get('/users/%s/starred' % self.username)

    def get_repo(self, full_name):
        return next(self._get('/repos/%s' % full_name))

    def get_top1k(self):
        return self._get('/search/repositories',
                         params={
                             'q': 'stars:>1',
                             'sort': 'stars',
                             'order': 'desc',
                             'per_page': 100,
                         })

    def compact(self, repo):
        return {
            'fork': repo['fork'],
            'full_name': repo['full_name'],
            'language': repo['language'],
            'description': repo['description']
        }
