# Acme CloudSync: Troubleshooting

Common error codes and how support should resolve them.

## Error E-102: sync conflict

Two users changed the same file at the same time. CloudSync keeps both versions and renames one with the suffix "(conflict copy)". Ask the customer to merge the changes manually.

## Error E-207: storage quota exceeded

The user has used all the storage included in their plan. New files stop syncing until space is freed. Suggest deleting old files or upgrading to a plan with more storage.

## Error E-311: authentication expired

The sign-in session has expired. The user must sign out of the desktop client and sign in again.

## Collecting logs

Client logs are stored in the ".cloudsync/logs" folder in the user's home directory. Ask customers to attach the latest log file to their ticket.
