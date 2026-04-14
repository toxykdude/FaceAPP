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
import { format } from 'date-fns';

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

    // Fetch users
    const { data: users, isLoading, refetch } = useQuery({
        queryKey: ['users'],
        queryFn: () => usersApi.getUsers(),
    });

    // Create mutation
    const createMutation = useMutation({
        mutationFn: (data: UserCreate) => usersApi.createUser(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            handleCloseDialog();
            setError(null);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || 'Failed to create user');
        },
    });

    // Update mutation
    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: UserUpdate }) =>
            usersApi.updateUser(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            handleCloseDialog();
            setError(null);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || 'Failed to update user');
        },
    });

    // Delete mutation
    const deleteMutation = useMutation({
        mutationFn: (id: string) => usersApi.deleteUser(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
        },
        onError: (err: any) => {
            alert(err.response?.data?.detail || 'Failed to delete user');
        },
    });

    // Password change mutation
    const passwordMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: PasswordChange }) =>
            usersApi.changePassword(id, data),
        onSuccess: () => {
            handleClosePasswordDialog();
            alert('Password changed successfully');
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || 'Failed to change password');
        },
    });

    const handleOpenCreate = () => {
        setEditingUser(null);
        setFormData({
            username: '',
            email: '',
            full_name: '',
            password: '',
            role: 'staff',
            is_active: true,
        });
        setPermissions(['all']);
        setError(null);
        setOpenDialog(true);
    };

    const handleOpenEdit = (user: User) => {
        setEditingUser(user);
        setFormData({
            username: user.username,
            email: user.email || '',
            full_name: user.full_name || '',
            password: '', // Don't populate password
            role: user.role,
            is_active: user.is_active,
        });
        setPermissions((user as any).permissions?.pages || ['all']);
        setError(null);
        setOpenDialog(true);
    };

    const handleCloseDialog = () => {
        setOpenDialog(false);
        setEditingUser(null);
        setError(null);
    };

    const handleOpenPasswordDialog = (userId: string) => {
        setPasswordUserId(userId);
        setPasswordData({
            current_password: '',
            new_password: '',
        });
        setError(null);
        setOpenPasswordDialog(true);
    };

    const handleClosePasswordDialog = () => {
        setOpenPasswordDialog(false);
        setPasswordUserId(null);
        setError(null);
    };

    const handleSubmit = () => {
        if (!formData.username) {
            setError('Username is required');
            return;
        }

        if (!editingUser && !formData.password) {
            setError('Password is required for new users');
            return;
        }

        if (editingUser) {
            // Update user
            const updateData: UserUpdate = {
                username: formData.username,
                email: formData.email || undefined,
                full_name: formData.full_name || undefined,
                role: formData.role,
                is_active: formData.is_active,
                permissions: { pages: permissions },
            };
            updateMutation.mutate({ id: editingUser.id, data: updateData });
        } else {
            // Create user
            createMutation.mutate({
                ...formData,
                permissions: { pages: permissions },
            });
        }
    };

    const handlePasswordSubmit = () => {
        if (!passwordData.new_password) {
            setError('New password is required');
            return;
        }

        if (passwordUserId) {
            // Only include current_password if it has a value
            const submitData: PasswordChange = {
                new_password: passwordData.new_password,
            };

            // Only add current_password if it's not empty
            if (passwordData.current_password) {
                submitData.current_password = passwordData.current_password;
            }

            passwordMutation.mutate({ id: passwordUserId, data: submitData });
        }
    };

    const handleDelete = (user: User) => {
        if (window.confirm(`Are you sure you want to delete user "${user.username}"?`)) {
            deleteMutation.mutate(user.id);
        }
    };

    if (isLoading) {
        return <Typography>Loading users...</Typography>;
    }

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h6" fontWeight="600">
                    User Management
                </Typography>
                <Box display="flex" gap={1}>
                    <IconButton onClick={() => refetch()} size="small">
                        <RefreshIcon />
                    </IconButton>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={handleOpenCreate}
                        sx={{ bgcolor: '#2e7d32', '&:hover': { bgcolor: '#1b5e20' } }}
                    >
                        Add User
                    </Button>
                </Box>
            </Box>

            <TableContainer component={Paper}>
                <Table>
                    <TableHead>
                        <TableRow>
                            <TableCell>Username</TableCell>
                            <TableCell>Full Name</TableCell>
                            <TableCell>Email</TableCell>
                            <TableCell>Role</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Permissions</TableCell>
                            <TableCell>Last Login</TableCell>
                            <TableCell align="right">Actions</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {users?.map((user) => (
                            <TableRow key={user.id}>
                                <TableCell>{user.username}</TableCell>
                                <TableCell>{user.full_name || '-'}</TableCell>
                                <TableCell>{user.email || '-'}</TableCell>
                                <TableCell>
                                    <Chip
                                        label={user.role.toUpperCase()}
                                        color={user.role === 'admin' ? 'error' : 'primary'}
                                        size="small"
                                    />
                                </TableCell>
                                <TableCell>
                                    <Chip
                                        label={user.is_active ? 'Active' : 'Inactive'}
                                        color={user.is_active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </TableCell>
                                <TableCell>
                                    {user.role === 'admin' ? (
                                        <Chip label="All" size="small" color="info" />
                                    ) : (
                                        <Tooltip title={((user as any).permissions?.pages || []).join(', ')}>
                                            <Chip
                                                label={((user as any).permissions?.pages || []).includes('all')
                                                    ? 'All'
                                                    : `${((user as any).permissions?.pages || []).length} pages`}
                                                size="small"
                                                variant="outlined"
                                            />
                                        </Tooltip>
                                    )}
                                </TableCell>
                                <TableCell>
                                    {user.last_login
                                        ? format(new Date(user.last_login), 'MMM dd, yyyy HH:mm')
                                        : 'Never'}
                                </TableCell>
                                <TableCell align="right">
                                    <Tooltip title="Change Password">
                                        <IconButton
                                            size="small"
                                            onClick={() => handleOpenPasswordDialog(user.id)}
                                        >
                                            <KeyIcon />
                                        </IconButton>
                                    </Tooltip>
                                    <Tooltip title="Edit User">
                                        <IconButton size="small" onClick={() => handleOpenEdit(user)}>
                                            <EditIcon />
                                        </IconButton>
                                    </Tooltip>
                                    <Tooltip title="Delete User">
                                        <IconButton
                                            size="small"
                                            color="error"
                                            onClick={() => handleDelete(user)}
                                        >
                                            <DeleteIcon />
                                        </IconButton>
                                    </Tooltip>
                                </TableCell>
                            </TableRow>
                        ))}
                        {(!users || users.length === 0) && (
                            <TableRow>
                                <TableCell colSpan={8} align="center">
                                    No users found
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Create/Edit User Dialog */}
            <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
                <DialogTitle>{editingUser ? 'Edit User' : 'Create New User'}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}

                        <TextField
                            label="Username"
                            fullWidth
                            required
                            value={formData.username}
                            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                        />

                        <TextField
                            label="Full Name"
                            fullWidth
                            value={formData.full_name}
                            onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                        />

                        <TextField
                            label="Email"
                            type="email"
                            fullWidth
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        />

                        {!editingUser && (
                            <TextField
                                label="Password"
                                type="password"
                                fullWidth
                                required
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                helperText="Minimum 8 characters"
                            />
                        )}

                        <FormControl fullWidth>
                            <InputLabel>Role</InputLabel>
                            <Select
                                value={formData.role}
                                label="Role"
                                onChange={(e) => setFormData({ ...formData, role: e.target.value as 'admin' | 'staff' })}
                            >
                                <MenuItem value="staff">Staff</MenuItem>
                                <MenuItem value="admin">Admin</MenuItem>
                            </Select>
                        </FormControl>

                        <FormControlLabel
                            control={
                                <Switch
                                    checked={formData.is_active}
                                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                />
                            }
                            label="Active"
                        />

                        {formData.role !== 'admin' && (
                            <Box sx={{ mt: 1 }}>
                                <Typography variant="subtitle2" gutterBottom>
                                    Page Permissions
                                </Typography>
                                <FormControlLabel
                                    control={
                                        <Checkbox
                                            checked={permissions.includes('all')}
                                            onChange={(e) => {
                                                if (e.target.checked) {
                                                    setPermissions(['all']);
                                                } else {
                                                    setPermissions([]);
                                                }
                                            }}
                                        />
                                    }
                                    label="All Pages"
                                />
                                {!permissions.includes('all') && (
                                    <FormGroup sx={{ ml: 2 }}>
                                        {PERMISSION_PAGES.map((p) => (
                                            <FormControlLabel
                                                key={p.key}
                                                control={
                                                    <Checkbox
                                                        checked={permissions.includes(p.key)}
                                                        onChange={(e) => {
                                                            if (e.target.checked) {
                                                                setPermissions([...permissions, p.key]);
                                                            } else {
                                                                setPermissions(permissions.filter(k => k !== p.key));
                                                            }
                                                        }}
                                                    />
                                                }
                                                label={p.label}
                                            />
                                        ))}
                                    </FormGroup>
                                )}
                            </Box>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>Cancel</Button>
                    <Button
                        onClick={handleSubmit}
                        variant="contained"
                        disabled={createMutation.isPending || updateMutation.isPending}
                    >
                        {createMutation.isPending || updateMutation.isPending
                            ? 'Saving...'
                            : editingUser
                                ? 'Update'
                                : 'Create'}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Change Password Dialog */}
            <Dialog open={openPasswordDialog} onClose={handleClosePasswordDialog} maxWidth="sm" fullWidth>
                <DialogTitle>Change Password</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}

                        <TextField
                            label="New Password"
                            type="password"
                            fullWidth
                            required
                            value={passwordData.new_password}
                            onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                            helperText="Minimum 8 characters"
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClosePasswordDialog}>Cancel</Button>
                    <Button
                        onClick={handlePasswordSubmit}
                        variant="contained"
                        disabled={passwordMutation.isPending}
                    >
                        {passwordMutation.isPending ? 'Changing...' : 'Change Password'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
