# PR Review Checklist

## Security
- [ ] No hardcoded secrets or credentials
- [ ] Input validation on all user-facing endpoints
- [ ] SQL injection / XSS prevention

## Performance
- [ ] No N+1 queries
- [ ] Pagination on list endpoints
- [ ] Proper indexing for new DB fields

## Compatibility
- [ ] API backward compatibility maintained
- [ ] Database migration is reversible
- [ ] Feature flags for gradual rollout
