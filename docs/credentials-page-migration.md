# Credentials page URL

As requested on 2026-09-16, the credential-management page now uses `/credentials`.
The former `/pool` URL is removed and returns 404; there is no redirect or alias.
Update bookmarks to `/credentials`. Sidebar navigation, provider result actions,
page styling and browser tests use the new page identifier.

The historical R1 compatibility fixture remains unchanged. Its comparison explicitly
requires the replacement credentials route, with a regression test for its removal.
Provider authentication, `/api/credentials` endpoints, stored credentials and internal
model/credential pooling behavior are unchanged. No data migration is required.
