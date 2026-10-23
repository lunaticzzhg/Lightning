REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'lightning_app'@'%';
-- MySQL requires UPDATE privilege for SELECT ... FOR UPDATE used to serialize code version creation.
GRANT SELECT, INSERT, UPDATE ON lightning.* TO 'lightning_app'@'%';
