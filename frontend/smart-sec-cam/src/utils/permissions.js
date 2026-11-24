export const isAdministrator = role => role === 'administrator' || role === 'admin';
export const canManageFootage = role => isAdministrator(role) || role === 'manager';
export const canManageSystem = role => isAdministrator(role);
export const canViewAudit = role => isAdministrator(role);
