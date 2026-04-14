import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    IconButton,
    Chip,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Switch,
    FormControlLabel,
    Checkbox,
    FormGroup,
    Alert,
    Tooltip,
} from '@mui/material';
import {
    Add as AddIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    Key as KeyIcon,
    Refresh as RefreshIcon,
} from '@mui/icons-material';
import { usersApi, User, UserCreate, UserUpdate, PasswordChange } from '@/api/users';
// date-fns removed - unused
import { useLanguage } from '@/i18n/LanguageContext';

const PERMISSION_PAGES = [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'members', label: 'Members' },
    { key: 'memberships', label: 'Memberships' },
    { key: 'cameras', label: 'Cameras' },
    { key: 'sales', label: 'Sales' },
    { key: 'reports', label: 'Reports' },
];

export const UserManagement: React.FC = () => {
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const [openDialog, setOpenDialog] = useState(false);
    const [openPasswordDialog, setOpenPasswordDialog] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);
    const [passwordUserId, setPasswordUserId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [permissions, setPermissions] = useState<string[]>(['all']);

    const [formData, setFormData] = useState<UserCreate>({
        username: '',
        email: '',
        full_name: '',
        password: '',
        role: 'staff',
        is_active: true,
    });

    const [passwordData, setPasswordData] = useState<PasswordChange>({
        current_password: '',
        new_password: '',
    });

    const { data: users, isLoading, refetch } = useQuery({
        queryKey: ['users'],
        queryFn: () => usersApi.getUsers(),
    });

    const createMutation = useMutation({
        mutationFn: (data: UserCreate) => usersApi.createUser(data),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['users'] }); handleCloseDialog(); setError(null); },
        onError: (err: any) => { setError(err.response?.data?.detail || t.settings.errorCreating); },
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: UserUpdate }) => usersApi.updateUser(id, data),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['users'] }); handleCloseDialog(); setError(null); },
        onError: (err: any) => { setError(err.response?.data?.detail || t.settings.errorUpdating); },
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => usersApi.deleteUser(id),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['users'] }); },
        onError: (err: any) => { alert(err.response?.data?.detail || 'Failed to delete user'); },
    });

    const passwordMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: PasswordChange }) => usersApi.changePassword(id, data),
        onSuccess: () => { handleClosePasswordDialog(); alert(t.settings.passwordChanged); },
        onError: (err: any) => { setError(err.response?.data?.detail || t.settings.errorChangingPassword); },
    });

    const handleOpenCreate = () => {
        setEditingUser(null);
        setFormData({ username: '', email: '', full_name: '', password: '', role: 'staff', is_active: true });
        setPermissions(['all']);
        setError(null);
        setOpenDialog(true);
    };

    const handleOpenEdit = (user: User) => {
        setEditingUser(user);
        setFormData({ username: user.username, email: user.email || '', full_name: user.full_name || '', password: '', role: user.role, is_active: user.is_active });
        setPermissions((user as any).permissions?.pages || ['all']);
        setError(null);
        setOpenDialog(true);
    };

    const handleCloseDialog = () => { setOpenDialog(false); setEditingUser(null); setError(null); };

    const handleOpenPasswordDialog = (userId: string) => {
        setPasswordUserId(userId);
        setPasswordData({ current_password: '', new_password: '' });
        setError(null);
        setOpenPasswordDialog(true);
    };

    const handleClosePasswordDialog = () => { setOpenPasswordDialog(false); setPasswordUserId(null); setError(null); };

    const handleSubmit = () => {
        if (!formData.username) { setError(t.settings.usernameRequired); return; }
        if (!editingUser && !formData.password) { setError(t.settings.passwordRequired); return; }
        if (editingUser) {
            const updateData: UserUpdate = { username: formData.username, email: formData.email || undefined, full_name: formData.full_name || undefined, role: formData.role, is_active: formData.is_active, permissions: { pages: permissions } };
            updateMutation.mutate({ id: editingUser.id, data: updateData });
        } else {
            createMutation.mutate({ ...formData, permissions: { pages: permissions } });
        }
    };

    const handlePasswordSubmit = () => {
        if (!passwordData.new_password) { setError(t.settings.newPasswordHelper); return; }
        if (passwordUserId) {
            const submitData: PasswordChange = { new_password: passwordData.new_password };
            if (passwordData.current_password) { submitData.current_password = passwordData.current_password; }
            passwordMutation.mutate({ id: passwordUserId, data: submitData });
        }
    };

    const handleDelete = (user: User) => {
        if (window.confirm(t.settings.deleteUserConfirm.replace('?', `"${user.username}"?`))) {
            deleteMutation.mutate(user.id);
        }
    };

    if (isLoading) {
        return <Typography>{t.settings.loadingUsers}</Typography>;
    }

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h6" fontWeight="600">{t.settings.userManagement}</Typography>
                <Box display="flex" gap={1}>
                    <IconButton onClick={() => refetch()} size="small"><RefreshIcon /></IconButton>
                    <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreate} sx={{ bgcolor: '#2e7d32', '&:hover': { bgcolor: '#1b5e20' } }}>
                        {t.settings.addNewUser}
                    </Button>
                </Box>
            </Box>

            <TableContainer component={Paper}>
                <Table>
                    <TableHead>
                        <TableRow>
                            <TableCell>{t.settings.username}</TableCell>
                            <TableCell>{t.settings.fullName}</TableCell>
                            <TableCell>{t.settings.email}</TableCell>
                            <TableCell>{t.settings.role}</TableCell>
                            <TableCell>{t.settings.status}</TableCell>
                            <TableCell>{t.settings.permissions}</TableCell>
                            <TableCell>{t.common.actions}</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {users?.map((user) => (
                            <TableRow key={user.id}>
                                <TableCell>{user.username}</TableCell>
                                <TableCell>{user.full_name || '-'}</TableCell>
                                <TableCell>{user.email || '-'}</TableCell>
                                <TableCell><Chip label={user.role.toUpperCase()} color={user.role === 'admin' ? 'error' : 'primary'} size="small" /></TableCell>
                                <TableCell><Chip label={user.is_active ? t.settings.isActive : t.members.inactive} color={user.is_active ? 'success' : 'default'} size="small" /></TableCell>
                                <TableCell>
                                    {user.role === 'admin' ? (
                                        <Chip label="All" size="small" color="info" />
                                    ) : (
                                        <Tooltip title={((user as any).permissions?.pages || []).join(', ')}>
                                            <Chip label={((user as any).permissions?.pages || []).includes('all') ? 'All' : `${((user as any).permissions?.pages || []).length} pages`} size="small" variant="outlined" />
                                        </Tooltip>
                                    )}
                                </TableCell>
                                <TableCell>
                                    <Tooltip title={t.settings.changePassword}><IconButton size="small" onClick={() => handleOpenPasswordDialog(user.id)}><KeyIcon /></IconButton></Tooltip>
                                    <Tooltip title={t.settings.edit}><IconButton size="small" onClick={() => handleOpenEdit(user)}><EditIcon /></IconButton></Tooltip>
                                    <Tooltip title={t.settings.deleteUser}><IconButton size="small" color="error" onClick={() => handleDelete(user)}><DeleteIcon /></IconButton></Tooltip>
                                </TableCell>
                            </TableRow>
                        ))}
                        {(!users || users.length === 0) && (
                            <TableRow><TableCell colSpan={8} align="center">{t.settings.noUsersFound}</TableCell></TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
                <DialogTitle>{editingUser ? t.settings.editUser : t.settings.createUser}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}
                        <TextField label={t.settings.username} fullWidth required value={formData.username} onChange={(e) => setFormData({ ...formData, username: e.target.value })} />
                        <TextField label={t.settings.fullName} fullWidth value={formData.full_name} onChange={(e) => setFormData({ ...formData, full_name: e.target.value })} />
                        <TextField label={t.settings.email} type="email" fullWidth value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} />
                        {!editingUser && (
                            <TextField label="Password" type="password" fullWidth required value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} helperText={t.settings.newPasswordHelper} />
                        )}
                        <FormControl fullWidth>
                            <InputLabel>{t.settings.role}</InputLabel>
                            <Select value={formData.role} label={t.settings.role} onChange={(e) => setFormData({ ...formData, role: e.target.value as 'admin' | 'staff' })}>
                                <MenuItem value="staff">{t.settings.staff}</MenuItem>
                                <MenuItem value="admin">{t.settings.admin}</MenuItem>
                            </Select>
                        </FormControl>
                        <FormControlLabel control={<Switch checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} />} label={t.settings.isActive} />
                        {formData.role !== 'admin' && (
                            <Box sx={{ mt: 1 }}>
                                <Typography variant="subtitle2" gutterBottom>{t.settings.pagePermissions}</Typography>
                                <FormControlLabel control={<Checkbox checked={permissions.includes('all')} onChange={(e) => { if (e.target.checked) { setPermissions(['all']); } else { setPermissions([]); } }} />} label={t.settings.allPages} />
                                {!permissions.includes('all') && (
                                    <FormGroup sx={{ ml: 2 }}>
                                        {PERMISSION_PAGES.map((p) => (
                                            <FormControlLabel key={p.key} control={<Checkbox checked={permissions.includes(p.key)} onChange={(e) => { if (e.target.checked) { setPermissions([...permissions, p.key]); } else { setPermissions(permissions.filter(k => k !== p.key)); } }} />} label={p.label} />
                                        ))}
                                    </FormGroup>
                                )}
                            </Box>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>{t.common.cancel}</Button>
                    <Button onClick={handleSubmit} variant="contained" disabled={createMutation.isPending || updateMutation.isPending}>
                        {createMutation.isPending || updateMutation.isPending ? t.settings.saving : editingUser ? t.common.edit : t.common.create}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={openPasswordDialog} onClose={handleClosePasswordDialog} maxWidth="sm" fullWidth>
                <DialogTitle>{t.settings.changePassword}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}
                        <TextField label={t.settings.newPassword} type="password" fullWidth required value={passwordData.new_password} onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })} helperText={t.settings.newPasswordHelper} />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClosePasswordDialog}>{t.common.cancel}</Button>
                    <Button onClick={handlePasswordSubmit} variant="contained" disabled={passwordMutation.isPending}>
                        {passwordMutation.isPending ? t.settings.saving : t.settings.changePassword}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
