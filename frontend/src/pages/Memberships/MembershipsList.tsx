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
    FormControlLabel,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import { Add as AddIcon, Refresh as RefreshIcon, Visibility as ViewIcon, Delete as DeleteIcon, Edit as EditIcon, CardMembership as PlanIcon, Assignment as AssignIcon } from '@mui/icons-material';
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi } from '@/api/membershipPlans';
import { format } from 'date-fns';
import { useLanguage } from '@/i18n/LanguageContext';

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
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const [tabValue, setTabValue] = useState(0);
    const [openPlanDialog, setOpenPlanDialog] = useState(false);

    const [newPlan, setNewPlan] = useState<CreatePlanDTO>({
        name: '',
        duration_days: 30,
        duration_months: 0,
        price: 0,
        description: '',
        is_active: true
    });

    const [editPlan, setEditPlan] = useState<any>(null);
    const [editFormData, setEditFormData] = useState<CreatePlanDTO>({
        name: '',
        duration_days: 30,
        duration_months: 0,
        price: 0,
        description: '',
        is_active: true
    });

    const { data: memberships, isLoading: loadingMemberships, refetch: refetchMemberships } = useQuery({
        queryKey: ['memberships'],
        queryFn: () => membershipsApi.getMemberships(),
    });

    const { data: plansData, refetch: refetchPlans } = useQuery({
        queryKey: ['membershipPlans'],
        queryFn: () => membershipPlansApi.getPlans(true),
    });
    const plans = plansData?.plans || [];

    const createPlanMutation = useMutation({
        mutationFn: (data: CreatePlanDTO) => membershipPlansApi.createPlan(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
            setOpenPlanDialog(false);
            setNewPlan({ name: '', duration_days: 30, duration_months: 0, price: 0, description: '', is_active: true });
        }
    });

    const handleCreatePlan = () => {
        createPlanMutation.mutate(newPlan);
    };

    const updatePlanMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: any }) => membershipPlansApi.updatePlan(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
            setEditPlan(null);
        },
    });

    const deletePlanMutation = useMutation({
        mutationFn: (id: string) => membershipPlansApi.deletePlan(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['membershipPlans'] });
        },
        onError: (error: any) => {
            alert('Error: ' + (error?.response?.data?.detail || error?.message || 'Unknown error'));
        },
    });

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
            case 'active': return <Chip label={t.memberships.active} color="success" size="small" />;
            case 'expired': return <Chip label={t.memberships.expired} color="error" size="small" />;
            case 'cancelled': return <Chip label={t.memberships.cancelled} color="warning" size="small" />;
            default: return <Chip label={status} size="small" />;
        }
    };

    return (
        <Box sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
            <Box display="flex" flexDirection={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} mb={3} gap={2}>
                <Typography variant={isMobile ? "h5" : "h4"}>{t.memberships.title}</Typography>
                <Box display="flex" gap={1} width={isMobile ? '100%' : 'auto'}>
                    <IconButton onClick={() => { refetchMemberships(); refetchPlans(); }} sx={{ minWidth: 44, minHeight: 44 }}>
                        <RefreshIcon />
                    </IconButton>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={() => {
                            if (tabValue === 0) navigate('/memberships/new');
                            else setOpenPlanDialog(true);
                        }}
                        fullWidth={isMobile}
                    >
                        {tabValue === 0 ? t.memberships.newMembership : t.memberships.addPlan}
                    </Button>
                </Box>
            </Box>

            <Tabs
                value={tabValue}
                onChange={(_, v) => setTabValue(v)}
                sx={{ mb: 3, overflowX: 'auto' }}
                variant="scrollable"
                scrollButtons="auto"
            >
                <Tab icon={<AssignIcon />} iconPosition="start" label={t.memberships.activePlans} />
                <Tab icon={<PlanIcon />} iconPosition="start" label={t.memberships.plans} />
            </Tabs>

            {tabValue === 0 && (
                <TableContainer component={Paper} sx={{ overflowX: 'auto' }}>
                    <Table size={isMobile ? "small" : "medium"}>
                        <TableHead>
                            <TableRow>
                                <TableCell>{t.memberships.member}</TableCell>
                                <TableCell>{t.memberships.type} / {t.memberships.plan}</TableCell>
                                {!isMobile && <TableCell>{t.memberships.startDate}</TableCell>}
                                <TableCell>{t.memberships.endDate}</TableCell>
                                <TableCell>{t.memberships.status}</TableCell>
                                <TableCell align="right">{t.common.actions}</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {memberships?.map((m) => (
                                <TableRow key={m.id}>
                                    <TableCell>
                                        <Typography variant="body2" fontWeight="bold">{m.member_name || t.dashboard.unknown}</Typography>
                                        {!isMobile && <Typography variant="caption" color="textSecondary">{m.member_id_number || t.memberships.noId}</Typography>}
                                    </TableCell>
                                    <TableCell>{m.plan_name || m.type}</TableCell>
                                    {!isMobile && <TableCell>{format(new Date(m.start_date + 'T12:00:00'), 'PPP')}</TableCell>}
                                    <TableCell>{format(new Date(m.end_date + 'T12:00:00'), 'PPP')}</TableCell>
                                    <TableCell>{getStatusChip(m.status)}</TableCell>
                                    <TableCell align="right">
                                        <IconButton size="small" onClick={() => navigate(`/members/${m.member_id}`)} title={t.memberships.viewMember} sx={{ minWidth: 44, minHeight: 44 }}><ViewIcon /></IconButton>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {(!memberships || memberships.length === 0) && (
                                <TableRow><TableCell colSpan={isMobile ? 5 : 6} align="center">{t.memberships.noMembershipsFound}</TableCell></TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            {tabValue === 1 && (
                <TableContainer component={Paper} sx={{ overflowX: 'auto' }}>
                    <Table size={isMobile ? "small" : "medium"}>
                        <TableHead>
                            <TableRow>
                                <TableCell>{t.memberships.planName}</TableCell>
                                <TableCell>{t.memberships.duration}</TableCell>
                                <TableCell>{t.memberships.price}</TableCell>
                                {!isMobile && <TableCell>{t.memberships.description}</TableCell>}
                                <TableCell>{t.memberships.status}</TableCell>
                                <TableCell align="right">{t.common.actions}</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {plans.map((p) => (
                                <TableRow key={p.id}>
                                    <TableCell sx={{ fontWeight: 'bold' }}>{p.name}</TableCell>
                                    <TableCell>
                                        {p.duration_months && p.duration_months > 0 ? `${p.duration_months} ${t.memberships.durationMonths} ` : ''}
                                        {p.duration_days > 0 ? `${p.duration_days} ${t.memberships.durationDays}` : ''}
                                    </TableCell>
                                    <TableCell>${p.price}</TableCell>
                                    {!isMobile && <TableCell>{p.description || '-'}</TableCell>}
                                    <TableCell>
                                        <Chip label={p.is_active ? t.memberships.active : t.members.inactive} color={p.is_active ? "success" : "default"} size="small" />
                                    </TableCell>
                                    <TableCell align="right">
                                        <IconButton size="small" onClick={() => setEditPlan(p)} sx={{ minWidth: 44, minHeight: 44 }}><EditIcon /></IconButton>
                                        <IconButton size="small" color="error" onClick={() => { if (confirm(`${t.memberships.deleteConfirm}`)) { deletePlanMutation.mutate(p.id); } }} sx={{ minWidth: 44, minHeight: 44 }}><DeleteIcon /></IconButton>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {plans.length === 0 && (
                                <TableRow><TableCell colSpan={isMobile ? 5 : 6} align="center">{t.memberships.noPlansFound}</TableCell></TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            )}

            {/* Create Plan Dialog */}
            <Dialog open={openPlanDialog} onClose={() => setOpenPlanDialog(false)} maxWidth="sm" fullWidth fullScreen={isMobile}>
                <DialogTitle>{t.memberships.createMembershipPlan}</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label={t.memberships.planName}
                            fullWidth
                            value={newPlan.name}
                            onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })}
                            placeholder="e.g. Gold Monthly"
                        />
                        <Grid container spacing={2}>
                            <Grid item xs={6}>
                                <TextField
                                    label={t.memberships.durationMonths}
                                    type="number"
                                    fullWidth
                                    value={newPlan.duration_months}
                                    onChange={(e) => setNewPlan({ ...newPlan, duration_months: Number(e.target.value) })}
                                />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField
                                    label={t.memberships.durationDays}
                                    type="number"
                                    fullWidth
                                    value={newPlan.duration_days}
                                    onChange={(e) => setNewPlan({ ...newPlan, duration_days: Number(e.target.value) })}
                                    helperText={t.memberships.additionalDays}
                                />
                            </Grid>
                        </Grid>
                        <TextField
                            label={t.memberships.price}
                            type="number"
                            fullWidth
                            value={newPlan.price}
                            onChange={(e) => setNewPlan({ ...newPlan, price: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <TextField
                            label={t.memberships.description}
                            fullWidth
                            multiline
                            rows={3}
                            value={newPlan.description}
                            onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })}
                        />
                        <FormControlLabel
                            control={<Switch checked={newPlan.is_active} onChange={(e) => setNewPlan({ ...newPlan, is_active: e.target.checked })} />}
                            label={t.memberships.activeAvailable}
                        />
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: { xs: 2, sm: 3 }, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
                    <Button onClick={() => setOpenPlanDialog(false)} fullWidth={isMobile}>{t.memberships.cancel}</Button>
                    <Button
                        onClick={handleCreatePlan}
                        variant="contained"
                        disabled={!newPlan.name || createPlanMutation.isPending}
                        fullWidth={isMobile}
                    >
                        {createPlanMutation.isPending ? t.memberships.creating : t.memberships.createPlan}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Edit Plan Dialog */}
            <Dialog open={!!editPlan} onClose={() => setEditPlan(null)} maxWidth="sm" fullWidth fullScreen={isMobile}>
                <DialogTitle>{t.memberships.editMembershipPlan}</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label={t.memberships.planName}
                            fullWidth
                            value={editFormData.name}
                            onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                            placeholder="e.g. Gold Monthly"
                        />
                        <Grid container spacing={2}>
                            <Grid item xs={6}>
                                <TextField
                                    label={t.memberships.durationMonths}
                                    type="number"
                                    fullWidth
                                    value={editFormData.duration_months}
                                    onChange={(e) => setEditFormData({ ...editFormData, duration_months: Number(e.target.value) })}
                                />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField
                                    label={t.memberships.durationDays}
                                    type="number"
                                    fullWidth
                                    value={editFormData.duration_days}
                                    onChange={(e) => setEditFormData({ ...editFormData, duration_days: Number(e.target.value) })}
                                    helperText={t.memberships.additionalDays}
                                />
                            </Grid>
                        </Grid>
                        <TextField
                            label={t.memberships.price}
                            type="number"
                            fullWidth
                            value={editFormData.price}
                            onChange={(e) => setEditFormData({ ...editFormData, price: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <TextField
                            label={t.memberships.description}
                            fullWidth
                            multiline
                            rows={3}
                            value={editFormData.description}
                            onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                        />
                        <FormControlLabel
                            control={<Switch checked={editFormData.is_active} onChange={(e) => setEditFormData({ ...editFormData, is_active: e.target.checked })} />}
                            label={t.memberships.activeAvailable}
                        />
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: { xs: 2, sm: 3 }, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
                    <Button onClick={() => setEditPlan(null)} fullWidth={isMobile}>{t.memberships.cancel}</Button>
                    <Button
                        onClick={handleUpdatePlan}
                        variant="contained"
                        disabled={!editFormData.name || updatePlanMutation.isPending}
                        fullWidth={isMobile}
                    >
                        {updatePlanMutation.isPending ? t.memberships.saving : t.memberships.saveChanges}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
