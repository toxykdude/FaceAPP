/**
 * Memberships list page.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Chip,
    CircularProgress,
    IconButton,
    Tabs,
    Tab,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Grid,
    InputAdornment,
    Switch,
    FormControlLabel
} from '@mui/material';
import { Add as AddIcon, Refresh as RefreshIcon, Visibility as ViewIcon, Delete as DeleteIcon, Edit as EditIcon, CardMembership as PlanIcon, Assignment as AssignIcon } from '@mui/icons-material';
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi } from '@/api/membershipPlans';
import { format } from 'date-fns';

interface CreatePlanDTO {
    name: string;
    duration_days: number;
    duration_months: number;
    price: number;
    description: string;
    is_active: boolean;
}

export const MembershipsList: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [tabValue, setTabValue] = useState(0);
    const [openPlanDialog, setOpenPlanDialog] = useState(false);

    // New Plan Form State
    const [newPlan, setNewPlan] = useState<CreatePlanDTO>({
        name: '',
        duration_days: 30,
        duration_months: 0,
        price: 0,
        description: '',
        is_active: true
    });

    // Edit Plan State
    const [editPlan, setEditPlan] = useState<any>(null);
    const [editFormData, setEditFormData] = useState<CreatePlanDTO>({
        name: '',
        duration_days: 30,
        duration_months: 0,
        price: 0,
        description: '',
        is_active: true
    });

    // Queries
    const { data: memberships, isLoading: loadingMemberships, refetch: refetchMemberships } = useQuery({
        queryKey: ['memberships'],
        queryFn: () => membershipsApi.getMemberships(),
    });

    const { data: plansData, refetch: refetchPlans } = useQuery({
        queryKey: ['membershipPlans'],
        queryFn: () => membershipPlansApi.getPlans(),
    });
    const plans = plansData?.plans || [];

    // Mutations
    const createPlanMutation = useMutation({
        mutationFn: (data: CreatePlanDTO) => membershipPlansApi.createPlan(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
            setOpenPlanDialog(false);
            setNewPlan({
                name: '',
                duration_days: 30,
                duration_months: 0,
                price: 0,
                description: '',
                is_active: true
            });
        }
    });

    const handleCreatePlan = () => {
        createPlanMutation.mutate(newPlan);
    };

    // Edit Plan Mutation
    const updatePlanMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: any }) => membershipPlansApi.updatePlan(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
            setEditPlan(null);
        },
    });

    // Delete Plan Mutation
    const deletePlanMutation = useMutation({
        mutationFn: (id: string) => membershipPlansApi.deletePlan(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
        },
    });

    // Sync edit form data when editPlan changes
    React.useEffect(() => {
        if (editPlan) {
            setEditFormData({
                name: editPlan.name,
                duration_days: editPlan.duration_days,
                duration_months: editPlan.duration_months,
                price: editPlan.price,
                description: editPlan.description || '',
                is_active: editPlan.is_active,
            });
        }
    }, [editPlan]);

    const handleUpdatePlan = () => {
        if (editPlan) {
            updatePlanMutation.mutate({ id: editPlan.id, data: editFormData });
        }
    };

    if (loadingMemberships && tabValue === 0) {
        return <Box display="flex" justifyContent="center" p={5}><CircularProgress /></Box>;
    }

    const getStatusChip = (status: string) => {
        switch (status) {
            case 'active': return <Chip label="Active" color="success" size="small" />;
            case 'expired': return <Chip label="Expired" color="error" size="small" />;
            case 'cancelled': return <Chip label="Cancelled" color="warning" size="small" />;
            default: return <Chip label={status} size="small" />;
        }
    };

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">Memberships</Typography>
                <Box>
                    <IconButton onClick={() => { refetchMemberships(); refetchPlans(); }} sx={{ mr: 1 }}>
                        <RefreshIcon />
                    </IconButton>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={() => {
                            if (tabValue === 0) navigate('/memberships/new'); // Existing manual add
                            else setOpenPlanDialog(true);
                        }}
                    >
                        {tabValue === 0 ? "New Membership" : "New Plan"}
                    </Button>
                </Box>
            </Box>

            <Tabs value={tabValue} onChange={(_, v) => setTabValue(v)} sx={{ mb: 3 }}>
                <Tab icon={<AssignIcon />} iconPosition="start" label="Active Memberships" />
                <Tab icon={<PlanIcon />} iconPosition="start" label="Membership Plans" />
            </Tabs>

            {/* TAB 0: Memberships List */}
            {tabValue === 0 && (
                <TableContainer component={Paper}>
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>Member</TableCell>
                                <TableCell>Type / Plan</TableCell>
                                <TableCell>Start Date</TableCell>
                                <TableCell>End Date</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell align="right">Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {memberships?.map((m) => (
                                <TableRow key={m.id}>
                                    <TableCell>
                                        <Typography variant="body2" fontWeight="bold">{m.member_name || 'Unknown'}</Typography>
                                        <Typography variant="caption" color="textSecondary">{m.member_id_number || 'No ID'}</Typography>
                                    </TableCell>
                                    <TableCell>{m.plan_name || m.type}</TableCell>
                                    <TableCell>{format(new Date(m.start_date), 'PPP')}</TableCell>
                                    <TableCell>{format(new Date(m.end_date), 'PPP')}</TableCell>
                                    <TableCell>{getStatusChip(m.status)}</TableCell>
                                    <TableCell align="right">
                                        <IconButton size="small" onClick={() => navigate(`/members/${m.member_id}`)} title="View Member"><ViewIcon /></IconButton>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {(!memberships || memberships.length === 0) && (
                                <TableRow><TableCell colSpan={6} align="center">No memberships found.</TableCell></TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            {/* TAB 1: Plans List */}
            {tabValue === 1 && (
                <TableContainer component={Paper}>
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>Plan Name</TableCell>
                                <TableCell>Duration</TableCell>
                                <TableCell>Price</TableCell>
                                <TableCell>Description</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell align="right">Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {plans.map((p) => (
                                <TableRow key={p.id}>
                                    <TableCell sx={{ fontWeight: 'bold' }}>{p.name}</TableCell>
                                    <TableCell>
                                        {p.duration_months && p.duration_months > 0 ? `${p.duration_months} Months ` : ''}
                                        {p.duration_days > 0 ? `${p.duration_days} Days` : ''}
                                    </TableCell>
                                    <TableCell>${p.price}</TableCell>
                                    <TableCell>{p.description || '-'}</TableCell>
                                    <TableCell>
                                        <Chip label={p.is_active ? "Active" : "Inactive"} color={p.is_active ? "success" : "default"} size="small" />
                                    </TableCell>
                                    <TableCell align="right">
                                        <IconButton size="small" onClick={() => setEditPlan(p)}><EditIcon /></IconButton>
                                        <IconButton size="small" color="error" onClick={() => { if (window.confirm(`Delete plan "${p.name}"?`)) deletePlanMutation.mutate(p.id); }}><DeleteIcon /></IconButton>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {plans.length === 0 && (
                                <TableRow><TableCell colSpan={6} align="center">No plans found. Create one to get started.</TableCell></TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            {/* Create Plan Dialog */}
            <Dialog open={openPlanDialog} onClose={() => setOpenPlanDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle>Create Membership Plan</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label="Plan Name"
                            fullWidth
                            value={newPlan.name}
                            onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })}
                            placeholder="e.g. Gold Monthly"
                        />
                        <Grid container spacing={2}>
                            <Grid item xs={6}>
                                <TextField
                                    label="Duration (Months)"
                                    type="number"
                                    fullWidth
                                    value={newPlan.duration_months}
                                    onChange={(e) => setNewPlan({ ...newPlan, duration_months: Number(e.target.value) })}
                                />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField
                                    label="Duration (Days)"
                                    type="number"
                                    fullWidth
                                    value={newPlan.duration_days}
                                    onChange={(e) => setNewPlan({ ...newPlan, duration_days: Number(e.target.value) })}
                                    helperText="Additional days"
                                />
                            </Grid>
                        </Grid>
                        <TextField
                            label="Price"
                            type="number"
                            fullWidth
                            value={newPlan.price}
                            onChange={(e) => setNewPlan({ ...newPlan, price: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <TextField
                            label="Description"
                            fullWidth
                            multiline
                            rows={3}
                            value={newPlan.description}
                            onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })}
                        />
                        <FormControlLabel
                            control={<Switch checked={newPlan.is_active} onChange={(e) => setNewPlan({ ...newPlan, is_active: e.target.checked })} />}
                            label="Active (Available for assignment)"
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenPlanDialog(false)}>Cancel</Button>
                    <Button
                        onClick={handleCreatePlan}
                        variant="contained"
                        disabled={!newPlan.name || createPlanMutation.isPending}
                    >
                        {createPlanMutation.isPending ? "Creating..." : "Create Plan"}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Edit Plan Dialog */}
            <Dialog open={!!editPlan} onClose={() => setEditPlan(null)} maxWidth="sm" fullWidth>
                <DialogTitle>Edit Membership Plan</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label="Plan Name"
                            fullWidth
                            value={editFormData.name}
                            onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                            placeholder="e.g. Gold Monthly"
                        />
                        <Grid container spacing={2}>
                            <Grid item xs={6}>
                                <TextField
                                    label="Duration (Months)"
                                    type="number"
                                    fullWidth
                                    value={editFormData.duration_months}
                                    onChange={(e) => setEditFormData({ ...editFormData, duration_months: Number(e.target.value) })}
                                />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField
                                    label="Duration (Days)"
                                    type="number"
                                    fullWidth
                                    value={editFormData.duration_days}
                                    onChange={(e) => setEditFormData({ ...editFormData, duration_days: Number(e.target.value) })}
                                    helperText="Additional days"
                                />
                            </Grid>
                        </Grid>
                        <TextField
                            label="Price"
                            type="number"
                            fullWidth
                            value={editFormData.price}
                            onChange={(e) => setEditFormData({ ...editFormData, price: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <TextField
                            label="Description"
                            fullWidth
                            multiline
                            rows={3}
                            value={editFormData.description}
                            onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                        />
                        <FormControlLabel
                            control={<Switch checked={editFormData.is_active} onChange={(e) => setEditFormData({ ...editFormData, is_active: e.target.checked })} />}
                            label="Active (Available for assignment)"
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setEditPlan(null)}>Cancel</Button>
                    <Button
                        onClick={handleUpdatePlan}
                        variant="contained"
                        disabled={!editFormData.name || updatePlanMutation.isPending}
                    >
                        {updatePlanMutation.isPending ? "Saving..." : "Save Changes"}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
